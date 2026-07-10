"""
Offer 投放业务服务层。

职责：
- Offer CRUD、分页列表与详情（客户角色仅能访问已分配渠道下的 Offer）
- 渠道分配（OfferPublisherAssignment）与短链接自动同步
- 创建/更新时生成下游 Tracklink、Postback URL，校验 publisher_configs
- 搜索支持 ID 精确匹配、上游 Offer ID、全文/前缀名称检索
- 写操作限管理员；变更后失效 Offer 缓存并写审计日志

注意：删除前检查点击记录；Tracklink 占位符规则与 app.core.url.placeholder 一致。

对应路由：app/api_v1/cpl/offers
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func, delete
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from app.models.models import (
    Offer, Advertiser, User,
    OfferPublisherAssignment, ShortLink, Click
)
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.audit_log import log_user_action
from app.core.infrastructure.cache import CacheInvalidator
from app.core.config import settings
from app.services.cpl.offer.helpers import (
    build_tracking_urls,
    extract_short_code_from_url,
    load_publishers_by_ids,
    parse_publisher_configs,
)
from app.services.cpl.offer.queries.assignments_query import OfferAssignmentsQuery
from app.services.cpl.offer.queries.detail_query import OfferDetailQuery
from app.services.cpl.offer.queries.list_query import OfferListQuery
import logging

logger = logging.getLogger(__name__)


def _get_sync_short_links_for_offer():
    """延迟导入短链接同步函数，避免 offer_service 与 API 层循环依赖。"""
    from app.api_v1.cpl.offers import sync_short_links_for_offer
    return sync_short_links_for_offer


class OfferService(BaseService[Offer]):
    """
    Offer 业务服务。

    Offer 是广告主与渠道之间的投放单元，承载追踪链接、
    出价、Cap 及渠道分配。客户用户仅能查看/操作已授权渠道关联的 Offer。
    """

    def __init__(self, db: AsyncSession):
        """注入异步数据库会话。"""
        super().__init__(db, Offer)

    async def get_offer_by_id(
            self,
            offer_id: int,
            current_user: User,
            include_advertiser: bool = True,
            include_assignments: bool = False
    ) -> Offer:
        return await OfferDetailQuery(self.db).fetch_by_id(
            offer_id,
            current_user,
            include_advertiser=include_advertiser,
            include_assignments=include_assignments,
        )

    async def get_offer_assignments(
            self,
            offer_id: int,
            current_user: User
    ) -> List[Dict[str, Any]]:
        return await OfferAssignmentsQuery(self.db).fetch_for_offer(offer_id, current_user)

    async def get_offers(
            self,
            current_user: User,
            page: int = 1,
            page_size: int = 20,
            search: Optional[str] = None,
            advertiser_id: Optional[int] = None,
            publisher_id: Optional[int] = None,
            status: Optional[str] = None,
            country: Optional[str] = None,
            is_active: Optional[bool] = None
    ) -> Tuple[List[Offer], int, Dict[int, List[Dict[str, Any]]]]:
        return await OfferListQuery(self.db).fetch(
            current_user=current_user,
            page=page,
            page_size=page_size,
            search=search,
            advertiser_id=advertiser_id,
            publisher_id=publisher_id,
            status=status,
            country=country,
            is_active=is_active,
        )

    async def create_offer(
            self,
            offer_data: Dict[str, Any],
            current_user: User
    ) -> Tuple[Offer, Optional[Dict[str, Any]]]:
        """
        创建 Offer（仅管理员），并可选同步渠道短链接。

        flush 后自动生成 downstream_tracklink 与 postback_url；
        publisher_configs 定义渠道分配及下游 Cap/PO。

        Args:
            offer_data: Offer 字段及 publisher_configs 列表
            current_user: 当前登录用户，须为管理员

        Returns:
            Tuple[Offer, Optional[Dict]]: (Offer 实体, 短链接同步结果或 None)

        Raises:
            APIException: 参数非法、渠道重复、唯一约束冲突等
        """
        # --- 权限与广告主校验 ---
        self.require_admin(current_user)

        # 验证广告主是否存在
        advertiser_id = offer_data.get('advertiser_id')
        if not advertiser_id:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="必须指定广告主ID"
            )

        advertiser_result = await self.db.execute(
            select(Advertiser).where(Advertiser.id == advertiser_id)
        )
        advertiser = advertiser_result.scalar_one_or_none()
        if not advertiser:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"广告主ID {advertiser_id} 不存在"
            )

        # 生成下游Tracklink和Postback URL
        base_url = settings.TRACKING_BASE_URL

        # 创建Offer（先不设置downstream_tracklink和postback_url，稍后设置）
        offer = Offer(
            offer_name=offer_data['offer_name'],
            advertiser_offer_id=offer_data.get('advertiser_offer_id'),
            advertiser_id=advertiser_id,
            preview_link=offer_data.get('preview_link'),
            payout=offer_data.get('payout'),
            affiliate_payout=offer_data.get('affiliate_payout'),
            country=offer_data.get('country'),
            category=offer_data.get('category'),
            type=offer_data.get('type'),
            status=offer_data.get('status', 'Active'),
            upstream_cap=offer_data.get('upstream_cap'),
            downstream_cap=offer_data.get('downstream_cap'),
            advertiser_tracklink=offer_data.get('advertiser_tracklink'),
            postback_method=offer_data.get('postback_method', 'GET'),
            click_validity_hours=offer_data.get('click_validity_hours', 720),
            is_active=offer_data.get('is_active', True)
        )

        self.db.add(offer)
        await self.db.flush()  # 先flush以获取offer.id

        downstream_tracklink, postback_url = build_tracking_urls(offer.id, base_url)
        offer.downstream_tracklink = downstream_tracklink
        offer.postback_url = postback_url

        publisher_ids_for_short_link = []
        publisher_configs = offer_data.get('publisher_configs')

        if publisher_configs is not None:
            parsed_publisher_configs = parse_publisher_configs(publisher_configs)
            if parsed_publisher_configs:
                pub_ids = [item[0] for item in parsed_publisher_configs]
                await load_publishers_by_ids(self.db, pub_ids)
                for pub_id, downstream_cap, affiliate_payout in parsed_publisher_configs:
                    assignment = OfferPublisherAssignment(
                        offer_id=offer.id,
                        publisher_id=pub_id,
                        downstream_cap=downstream_cap,
                        affiliate_payout=affiliate_payout,
                        is_active=True
                    )
                    self.db.add(assignment)
                    publisher_ids_for_short_link.append(pub_id)

        try:
            await self.db.flush()
            await self.db.refresh(offer)
        except IntegrityError as e:
            await self.db.rollback()
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            # 检查是否是唯一约束冲突（offer_id + publisher_id）
            if "uq_offer_publisher" in error_msg or "Duplicate entry" in error_msg:
                raise_api_exception(
                    ErrorCode.CONFLICT,
                    detail="渠道配置中存在重复的Offer-渠道组合，可能是并发操作导致的。请刷新后重试。"
                )
            # 其他完整性约束错误
            logger.error(f"创建Offer时数据库完整性约束违反: {error_msg}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"创建Offer失败: 数据库约束违反"
            )

        # 为分配的渠道创建短链接（使用上游Tracklink作为原始URL）
        short_link_info = None
        if publisher_ids_for_short_link and offer.advertiser_tracklink:
            # 延迟导入，避免循环导入
            sync_short_links_for_offer = _get_sync_short_links_for_offer()
            short_link_info = await sync_short_links_for_offer(
                db=self.db,
                offer_id=offer.id,
                publisher_ids=publisher_ids_for_short_link,
                offer_name=offer.offer_name,
                base_url=base_url,
                current_user_id=current_user.id,
                advertiser_tracklink=offer.advertiser_tracklink
            )
            await self.db.flush()
            await self.db.refresh(offer)
        elif publisher_ids_for_short_link and not offer.advertiser_tracklink:
            logger.warning(f"Offer {offer.id} 没有配置上游Tracklink，无法创建短链接")

        # 失效相关缓存
        await CacheInvalidator.invalidate_offer_cache(offer.id)

        # 记录审计日志
        await log_user_action(
            db=self.db,
            action_type="CREATE",
            user=current_user,
            username=current_user.username,
            resource_type="OFFER",
            resource_id=offer.id,
            resource_name=offer.offer_name,
            success=True
        )
        logger.info(f"Offer已创建: {offer.offer_name} (ID: {offer.id})")
        return offer, short_link_info

    async def update_offer(
            self,
            offer_id: int,
            offer_data: Dict[str, Any],
            current_user: User
    ) -> Tuple[Offer, Optional[Dict[str, Any]], Optional[Dict[str, Any]], bool]:
        """
        更新 Offer（仅管理员），同步渠道分配与短链接。

        advertiser_tracklink 变更时尝试更新主短链 original_url；
        publisher_configs 变更或上游链接变更时触发短链接同步。

        Args:
            offer_id: Offer 主键
            offer_data: 待更新字段，可含 publisher_configs
            current_user: 当前登录用户，须为管理员

        Returns:
            Tuple[Offer, Optional[Dict], Optional[Dict], bool]:
                (Offer, 渠道短链同步信息, 下游 Tracklink 短链信息,
                 downstream_tracklink 是否发生变更)
        """
        # --- 权限校验 ---
        self.require_admin(current_user)

        # 获取Offer
        offer = await self.get_offer_by_id(offer_id, current_user, include_advertiser=False)

        # 保存旧的tracklink，用于检测变化
        old_downstream_tracklink = offer.downstream_tracklink
        old_advertiser_tracklink = offer.advertiser_tracklink

        # 验证广告主是否存在（如果修改）
        if 'advertiser_id' in offer_data and offer_data['advertiser_id'] != offer.advertiser_id:
            advertiser_result = await self.db.execute(
                select(Advertiser).where(Advertiser.id == offer_data['advertiser_id'])
            )
            advertiser = advertiser_result.scalar_one_or_none()
            if not advertiser:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"广告主ID {offer_data['advertiser_id']} 不存在"
                )
            offer.advertiser_id = offer_data['advertiser_id']

        # 检查advertiser_tracklink是否改变（在更新字段之前检查，以便获取旧的downstream_tracklink）
        advertiser_tracklink_changed = False
        new_advertiser_tracklink = None
        if 'advertiser_tracklink' in offer_data:
            new_advertiser_tracklink = offer_data.get('advertiser_tracklink')
            if new_advertiser_tracklink != old_advertiser_tracklink:
                advertiser_tracklink_changed = True
                logger.info(
                    f"检测到advertiser_tracklink变化: "
                    f"offer_id={offer_id}, "
                    f"old={old_advertiser_tracklink}, "
                    f"new={new_advertiser_tracklink}"
                )

                # 如果上游Tracklink改变，且下游Tracklink是短链接，更新短链接的原始URL
                # 注意：这里使用当前的downstream_tracklink（更新前的值）
                current_downstream_tracklink = offer.downstream_tracklink
                if current_downstream_tracklink and new_advertiser_tracklink:
                    try:
                        # 从下游Tracklink中提取short_code
                        # 格式可能是: {base_url}/s/{short_code} 或 {base_url}/s/{short_code}?offer_id=X&channel_id=Y
                        short_code = extract_short_code_from_url(current_downstream_tracklink)
                        if short_code:
                            # 查找对应的短链接记录
                            short_link_result = await self.db.execute(
                                select(ShortLink).where(
                                    and_(
                                        ShortLink.short_code == short_code,
                                        ShortLink.offer_id == offer_id,
                                        ShortLink.channel_id.is_(None)  # 主短链接
                                    )
                                )
                            )
                            short_link = short_link_result.scalars().first()

                            if short_link:
                                # 更新短链接的原始URL（不在这里commit，统一在最后提交）
                                old_original_url = short_link.original_url
                                short_link.original_url = new_advertiser_tracklink.strip()
                                logger.info(
                                    f"已更新短链接的原始URL: "
                                    f"offer_id={offer_id}, "
                                    f"short_code={short_code}, "
                                    f"old_original_url={old_original_url}, "
                                    f"new_original_url={new_advertiser_tracklink}"
                                )
                            else:
                                logger.warning(
                                    f"未找到对应的短链接记录: "
                                    f"offer_id={offer_id}, "
                                    f"short_code={short_code}"
                                )
                    except Exception as e:
                        # 如果更新短链接失败，记录错误但不影响Offer更新
                        logger.error(
                            f"更新短链接原始URL失败（不影响Offer更新）: "
                            f"offer_id={offer_id}, "
                            f"error={str(e)}",
                            exc_info=True
                        )

        # 更新其他字段（排除渠道配置）
        update_fields = [
            'offer_name', 'advertiser_offer_id', 'preview_link', 'payout',
            'affiliate_payout', 'country', 'category', 'type', 'status',
            'upstream_cap', 'downstream_cap', 'advertiser_tracklink',
            'downstream_tracklink', 'postback_url', 'postback_method',
            'click_validity_hours', 'is_active'
        ]

        for field in update_fields:
            if field in offer_data:
                setattr(offer, field, offer_data[field])

        # 检查downstream_tracklink是否改变
        downstream_tracklink_changed = False
        if 'downstream_tracklink' in offer_data:
            new_downstream_tracklink = offer_data.get('downstream_tracklink')
            if new_downstream_tracklink != old_downstream_tracklink:
                downstream_tracklink_changed = True
                logger.info(
                    f"检测到downstream_tracklink变化: "
                    f"offer_id={offer_id}, "
                    f"old={old_downstream_tracklink}, "
                    f"new={new_downstream_tracklink}"
                )

        # 处理渠道分配
        old_publisher_ids = None
        publisher_ids_for_short_link = []
        publisher_configs = offer_data.get('publisher_configs')

        if publisher_configs is not None:
            old_assignments_result = await self.db.execute(
                select(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
            )
            old_assignments = old_assignments_result.scalars().all()
            old_publisher_ids = {assignment.publisher_id for assignment in old_assignments}

            await self.db.execute(
                delete(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
            )

            parsed_publisher_configs = parse_publisher_configs(publisher_configs)
            if parsed_publisher_configs:
                pub_ids = [item[0] for item in parsed_publisher_configs]
                await load_publishers_by_ids(self.db, pub_ids)
                for pub_id, downstream_cap, affiliate_payout in parsed_publisher_configs:
                    assignment = OfferPublisherAssignment(
                        offer_id=offer.id,
                        publisher_id=pub_id,
                        downstream_cap=downstream_cap,
                        affiliate_payout=affiliate_payout,
                        is_active=True
                    )
                    self.db.add(assignment)
                    publisher_ids_for_short_link.append(pub_id)

        try:
            await self.db.flush()
            await self.db.refresh(offer)
        except IntegrityError as e:
            await self.db.rollback()
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            # 检查是否是唯一约束冲突（offer_id + publisher_id）
            if "uq_offer_publisher" in error_msg or "Duplicate entry" in error_msg:
                raise_api_exception(
                    ErrorCode.CONFLICT,
                    detail="渠道配置中存在重复的Offer-渠道组合，可能是并发操作导致的。请刷新后重试。"
                )
            # 其他完整性约束错误
            logger.error(f"更新Offer时数据库完整性约束违反: {error_msg}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新Offer失败: 数据库约束违反"
            )

        # 移除旧的删除逻辑，改为在sync_short_links_for_offer中处理
        # 这样可以保持短码不变，只更新原始URL

        # 如果渠道分配有变化或advertiser_tracklink改变，同步短链接
        short_link_info = None
        need_sync_short_links = False

        # 检查是否需要同步短链接
        if publisher_configs is not None:
            new_publisher_ids = set(publisher_ids_for_short_link)
            if old_publisher_ids != new_publisher_ids:
                need_sync_short_links = True
        elif advertiser_tracklink_changed:
            need_sync_short_links = True

        if need_sync_short_links:
            # 获取当前的上游Tracklink（可能是新更新的）
            current_advertiser_tracklink = offer.advertiser_tracklink
            # 获取当前的渠道分配
            if publisher_configs is not None:
                current_publisher_ids = publisher_ids_for_short_link
            else:
                # 如果没有明确指定publisher_ids，使用现有的分配
                existing_assignments_result = await self.db.execute(
                    select(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
                )
                existing_assignments = existing_assignments_result.scalars().all()
                current_publisher_ids = [assignment.publisher_id for assignment in existing_assignments]

            if current_advertiser_tracklink and current_publisher_ids:
                # 延迟导入，避免循环导入
                sync_short_links_for_offer = _get_sync_short_links_for_offer()
                base_url = settings.TRACKING_BASE_URL
                short_link_info = await sync_short_links_for_offer(
                    db=self.db,
                    offer_id=offer.id,
                    publisher_ids=current_publisher_ids,
                    offer_name=offer.offer_name,
                    base_url=base_url,
                    current_user_id=current_user.id,
                    advertiser_tracklink=current_advertiser_tracklink
                )
                await self.db.flush()
                await self.db.refresh(offer)
            elif not current_advertiser_tracklink:
                logger.warning(f"Offer {offer.id} 没有配置上游Tracklink，无法创建短链接")

        # 检查下游Tracklink是否在short_links表中存在，如果不存在则创建
        downstream_tracklink_short_link_info = None
        current_downstream_tracklink = offer.downstream_tracklink
        current_advertiser_tracklink = offer.advertiser_tracklink
        if current_downstream_tracklink and current_advertiser_tracklink:
            from app.api_v1.cpl.offers import (
                check_and_create_downstream_tracklink_short_link,
                get_short_link_url
            )
            base_url = settings.TRACKING_BASE_URL
            try:
                downstream_short_link, is_new = await check_and_create_downstream_tracklink_short_link(
                    db=self.db,
                    offer_id=offer.id,
                    downstream_tracklink=current_downstream_tracklink,
                    advertiser_tracklink=current_advertiser_tracklink,
                    offer_name=offer.offer_name,
                    base_url=base_url,
                    current_user_id=current_user.id
                )

                if downstream_short_link:
                    short_link_url = get_short_link_url(base_url, downstream_short_link.short_code)
                    downstream_tracklink_short_link_info = {
                        'short_link': downstream_short_link,
                        'short_link_url': short_link_url,
                        'is_new': is_new
                    }

                    # 更新offer.downstream_tracklink为短链接URL
                    offer.downstream_tracklink = short_link_url
                    await self.db.flush()
                    await self.db.refresh(offer)
            except Exception as e:
                # 如果创建短链接失败，记录错误但不影响Offer更新
                error_msg = str(e)
                logger.error(
                    f"创建下游Tracklink短链接失败（不影响Offer更新）: "
                    f"offer_id={offer.id}, "
                    f"error={error_msg[:200]}"
                )

        # 失效相关缓存
        await CacheInvalidator.invalidate_offer_cache(offer.id)

        # 记录审计日志
        await log_user_action(
            db=self.db,
            action_type="UPDATE",
            user=current_user,
            username=current_user.username,
            resource_type="OFFER",
            resource_id=offer.id,
            resource_name=offer.offer_name,
            success=True
        )
        logger.info(f"Offer已更新: {offer.offer_name} (ID: {offer.id})")
        return offer, short_link_info, downstream_tracklink_short_link_info, downstream_tracklink_changed

    async def delete_offer(
            self,
            offer_id: int,
            current_user: User
    ) -> None:
        """
        删除 Offer（仅管理员）。

        若存在关联点击记录则拒绝删除，保护历史归因数据。

        Args:
            offer_id: Offer 主键
            current_user: 当前登录用户，须为管理员

        Raises:
            APIException: 存在点击记录或记录不存在
        """
        # --- 权限校验 ---
        self.require_admin(current_user)

        # 获取Offer
        offer = await self.get_offer_by_id(offer_id, current_user, include_advertiser=False)

        # 检查是否有关联的点击记录
        click_count = await self.db.execute(
            select(func.count(Click.id)).where(Click.offer_id == offer_id)
        )
        if click_count.scalar() > 0:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"Offer {offer.offer_name} 有关联的点击记录，无法删除"
            )

        # 记录审计日志（在删除前）
        await log_user_action(
            db=self.db,
            action_type="DELETE",
            user=current_user,
            username=current_user.username,
            resource_type="OFFER",
            resource_id=offer.id,
            resource_name=offer.offer_name,
            success=True
        )

        # 删除Offer
        await self.db.delete(offer)
        await self.db.flush()

        logger.info(f"Offer已删除: {offer.offer_name} (ID: {offer_id})")
