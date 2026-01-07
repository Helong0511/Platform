"""
Offer服务层
封装Offer相关的业务逻辑，优化数据库查询
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, String, and_, or_, delete
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from app.models.models import (
    Offer, Advertiser, Publisher, Client, User, UserRole,
    OfferPublisherAssignment, ShortLink
)
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.audit_log import log_user_action
from app.core.infrastructure.cache import CacheInvalidator
import logging

logger = logging.getLogger(__name__)


class OfferService(BaseService[Offer]):
    """Offer服务"""
    
    def __init__(self, db: AsyncSession):
        super().__init__(db, Offer)
    
    async def get_offer_by_id(
        self,
        offer_id: int,
        current_user: User,
        include_advertiser: bool = True,
        include_assignments: bool = False
    ) -> Offer:
        """
        根据ID获取Offer详情（优化查询，避免N+1问题，包含权限检查）
        
        Args:
            offer_id: Offer ID
            current_user: 当前用户
            include_advertiser: 是否包含广告主信息
            include_assignments: 是否包含渠道分配信息
        
        Returns:
            Offer: Offer对象
        
        Raises:
            HTTPException: 如果Offer不存在或用户无权访问
        """
        # 权限检查：客户只能查看分配给自己的渠道的Offer
        if current_user.role == UserRole.CLIENT:
            # 获取当前用户的client_id
            client_result = await self.db.execute(
                select(Client.id).where(Client.user_id == current_user.id).limit(1)
            )
            client_id = client_result.scalar_one_or_none()
            
            if client_id:
                # 检查该Offer是否分配给该客户的渠道（只检查激活的渠道和激活的分配）
                check_result = await self.db.execute(
                    select(OfferPublisherAssignment)
                    .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
                    .where(
                        and_(
                            OfferPublisherAssignment.offer_id == offer_id,
                            Publisher.client_id == client_id,
                            Publisher.is_active == True,
                            OfferPublisherAssignment.is_active == True
                        )
                    )
                    .limit(1)
                )
                if not check_result.scalar_one_or_none():
                    raise_api_exception(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        detail=f"Offer ID {offer_id} 不存在或无权访问"
                    )
            else:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"Offer ID {offer_id} 不存在或无权访问"
                )
        
        query = select(Offer).where(Offer.id == offer_id)
        
        # 使用joinedload/selectinload优化关联查询
        options = []
        if include_advertiser:
            options.append(joinedload(Offer.advertiser))
        if include_assignments:
            options.append(selectinload(Offer.offer_assignments).joinedload(OfferPublisherAssignment.publisher))
        
        if options:
            query = query.options(*options)
        
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        # 注意：scalar_one_or_none()用于标量值，这里应该使用scalars().one_or_none()
        if options:
            offer = result.unique().scalars().one_or_none()
        else:
            offer = result.scalars().one_or_none()
        
        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {offer_id} 不存在"
            )
        
        return offer
    
    async def get_offer_assignments(
        self,
        offer_id: int,
        current_user: User
    ) -> List[Dict[str, Any]]:
        """
        获取Offer的渠道分配列表（优化查询，批量加载）
        
        Args:
            offer_id: Offer ID
            current_user: 当前用户
        
        Returns:
            List[Dict]: 渠道分配列表
        """
        # 加载分配的渠道（只加载激活的渠道和激活的分配）
        pub_query = (
            select(OfferPublisherAssignment, Publisher)
            .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
            .where(OfferPublisherAssignment.offer_id == offer_id)
            .where(OfferPublisherAssignment.is_active == True)
            .where(Publisher.is_active == True)
        )
        
        # 如果是客户用户，只加载属于该客户的渠道
        if current_user.role == UserRole.CLIENT:
            client_result = await self.db.execute(
                select(Client.id).where(Client.user_id == current_user.id).limit(1)
            )
            client_id = client_result.scalar_one_or_none()
            if client_id:
                pub_query = pub_query.where(Publisher.client_id == client_id)
        
        pub_result = await self.db.execute(pub_query)
        assignments = pub_result.all()
        
        return [
            {
                "id": pub.id,
                "publisher_name": pub.publisher_name,
                "client_id": pub.client_id,
                "downstream_cap": assignment.downstream_cap,
                "affiliate_payout": assignment.affiliate_payout
            }
            for assignment, pub in assignments
        ]
    
    async def get_offers(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        status: Optional[str] = None,
        country: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[List[Offer], int, Dict[int, List[Dict[str, Any]]]]:
        """
        获取Offer列表（优化查询，批量加载关联数据）
        
        Args:
            current_user: 当前用户
            page: 页码
            page_size: 每页数量
            search: 搜索关键词
            advertiser_id: 广告主ID过滤
            status: 状态过滤
            country: 国家过滤
            is_active: 激活状态过滤
        
        Returns:
            tuple: (Offer列表, 总数, 渠道分配映射)
        """
        query = select(Offer)
        
        # 权限过滤：客户只能查看分配给自己的渠道的Offer
        if current_user.role == UserRole.CLIENT:
            # 获取当前用户的client_id
            client_result = await self.db.execute(
                select(Client.id).where(Client.user_id == current_user.id).limit(1)
            )
            client_id = client_result.scalar_one_or_none()
            
            if client_id:
                # 通过join过滤：只返回分配给该客户渠道的Offer
                query = query.join(
                    OfferPublisherAssignment, Offer.id == OfferPublisherAssignment.offer_id
                ).join(
                    Publisher, OfferPublisherAssignment.publisher_id == Publisher.id
                ).where(
                    and_(
                        Publisher.client_id == client_id,
                        Publisher.is_active == True,
                        OfferPublisherAssignment.is_active == True
                    )
                ).distinct()
            else:
                # 如果客户没有关联的Client记录，返回空列表
                return [], 0, {}
        
        # 筛选条件
        conditions = []
        
        if search:
            # 搜索：名称、ID或上游Offer ID
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    Offer.offer_name.like(search_pattern),
                    Offer.id.cast(String).like(search_pattern),
                    Offer.advertiser_offer_id.like(search_pattern)
                )
            )
        
        if advertiser_id:
            conditions.append(Offer.advertiser_id == advertiser_id)
        
        if status:
            conditions.append(Offer.status == status)
        
        if country:
            conditions.append(Offer.country == country)
        
        if is_active is not None:
            conditions.append(Offer.is_active == is_active)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 总数查询（优化：不加载关联数据）
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页查询（使用joinedload优化广告主加载）
        offset = (page - 1) * page_size
        query = query.options(joinedload(Offer.advertiser))
        query = query.order_by(Offer.created_at.desc())
        query = query.offset(offset).limit(page_size)
        
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        offers = result.unique().scalars().all()
        
        # 批量加载所有offer的渠道分配（避免N+1查询）
        assignments_map = {}
        offer_ids = [offer.id for offer in offers]
        
        if offer_ids:
            # 构建渠道分配查询（批量加载）
            pub_query = (
                select(OfferPublisherAssignment, Publisher)
                .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
                .where(OfferPublisherAssignment.offer_id.in_(offer_ids))
                .where(OfferPublisherAssignment.is_active == True)
                .where(Publisher.is_active == True)
            )
            
            # 如果是客户用户，只加载属于该客户的渠道
            if current_user.role == UserRole.CLIENT:
                client_result = await self.db.execute(
                    select(Client.id).where(Client.user_id == current_user.id).limit(1)
                )
                client_id = client_result.scalar_one_or_none()
                if client_id:
                    pub_query = pub_query.where(Publisher.client_id == client_id)
            
            pub_result = await self.db.execute(pub_query)
            for assignment, publisher in pub_result.all():
                if assignment.offer_id not in assignments_map:
                    assignments_map[assignment.offer_id] = []
                assignments_map[assignment.offer_id].append({
                    "id": publisher.id,
                    "publisher_name": publisher.publisher_name,
                    "client_id": publisher.client_id,
                    "downstream_cap": assignment.downstream_cap,
                    "affiliate_payout": assignment.affiliate_payout
                })
        
        return offers, total, assignments_map
    
    async def create_offer(
        self,
        offer_data: Dict[str, Any],
        current_user: User
    ) -> Tuple[Offer, Optional[Dict[str, Any]]]:
        """
        创建Offer（支持渠道分配和短链接创建）
        
        Args:
            offer_data: Offer数据字典（可能包含publisher_configs或publisher_ids）
            current_user: 当前用户
        
        Returns:
            Tuple[Offer, Optional[Dict]]: (创建的Offer对象, 短链接信息)
        """
        # 权限检查：仅管理员可创建
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
        from app.core.config import settings
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
        
        # 生成下游Tracklink和Postback URL
        downstream_tracklink = f"{base_url.rstrip('/')}/api/v1/track/click/{offer.id}?publisher_id={{publisher_id}}"
        postback_url = f"{base_url.rstrip('/')}/api/v1/postback?click_id={{click_id}}&offer_id={offer.id}"
        offer.downstream_tracklink = downstream_tracklink
        offer.postback_url = postback_url
        
        # 处理渠道分配
        publisher_ids_for_short_link = []
        publisher_configs = offer_data.get('publisher_configs')
        publisher_ids = offer_data.get('publisher_ids')
        
        if publisher_configs is not None:
            # 使用新的渠道配置方式
            if len(publisher_configs) == 0:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="渠道配置不能为空，请至少添加一个渠道"
                )
            
            # 验证是否有重复的publisher_id（先过滤None值，因为None会在后面单独验证）
            publisher_id_list = [
                config.get('publisher_id') if isinstance(config, dict) else config.publisher_id 
                for config in publisher_configs
            ]
            # 过滤掉None值，因为None会在后面单独验证
            valid_publisher_ids = [pid for pid in publisher_id_list if pid is not None]
            if len(valid_publisher_ids) != len(set(valid_publisher_ids)):
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="渠道配置中存在重复的渠道ID"
                )
            
            for config in publisher_configs:
                # 处理字典或对象
                if isinstance(config, dict):
                    pub_id = config.get('publisher_id')
                    downstream_cap = config.get('downstream_cap')
                    affiliate_payout = config.get('affiliate_payout')
                else:
                    pub_id = config.publisher_id
                    downstream_cap = config.downstream_cap
                    affiliate_payout = config.affiliate_payout
                
                # 验证publisher_id是否存在且有效
                if pub_id is None:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail="渠道配置中的publisher_id不能为空，请确保已选择渠道"
                    )
                
                # 验证publisher_id类型（必须是整数）
                try:
                    pub_id = int(pub_id)
                except (ValueError, TypeError):
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail=f"渠道配置中的publisher_id必须是整数，当前值: {pub_id} (类型: {type(pub_id).__name__})"
                    )
                
                # 验证publisher_id范围（必须大于0）
                if pub_id <= 0:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail=f"渠道配置中的publisher_id必须大于0，当前值: {pub_id}"
                    )
                
                # 验证downstream_cap和affiliate_payout不能为负数
                # 同时验证类型（downstream_cap必须是整数或None，affiliate_payout必须是浮点数或None）
                if downstream_cap is not None:
                    try:
                        downstream_cap = int(downstream_cap)
                    except (ValueError, TypeError):
                        raise_api_exception(
                            ErrorCode.INVALID_PARAMETER,
                            detail=f"渠道ID {pub_id} 的下游Cap必须是整数，当前值: {downstream_cap} (类型: {type(downstream_cap).__name__})"
                        )
                
                if affiliate_payout is not None:
                    try:
                        affiliate_payout = float(affiliate_payout)
                    except (ValueError, TypeError):
                        raise_api_exception(
                            ErrorCode.INVALID_PARAMETER,
                            detail=f"渠道ID {pub_id} 的下游PO必须是数字，当前值: {affiliate_payout} (类型: {type(affiliate_payout).__name__})"
                        )
                
                # 验证downstream_cap和affiliate_payout不能为负数
                if downstream_cap is not None and downstream_cap < 0:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail=f"渠道ID {pub_id} 的下游Cap不能为负数"
                    )
                
                if affiliate_payout is not None and affiliate_payout < 0:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail=f"渠道ID {pub_id} 的下游PO不能为负数"
                    )
                
                # 验证渠道是否存在
                pub_result = await self.db.execute(
                    select(Publisher).where(Publisher.id == pub_id)
                )
                publisher = pub_result.scalar_one_or_none()
                if not publisher:
                    raise_api_exception(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        detail=f"渠道ID {pub_id} 不存在"
                    )
                
                assignment = OfferPublisherAssignment(
                    offer_id=offer.id,
                    publisher_id=pub_id,
                    downstream_cap=downstream_cap,
                    affiliate_payout=affiliate_payout,
                    is_active=True
                )
                self.db.add(assignment)
                publisher_ids_for_short_link.append(pub_id)
        elif publisher_ids:
            # 向后兼容：使用旧的publisher_ids方式
            for pub_id in publisher_ids:
                # 验证渠道是否存在
                pub_result = await self.db.execute(
                    select(Publisher).where(Publisher.id == pub_id)
                )
                publisher = pub_result.scalar_one_or_none()
                if publisher:
                    assignment = OfferPublisherAssignment(
                        offer_id=offer.id,
                        publisher_id=pub_id,
                        is_active=True
                    )
                    self.db.add(assignment)
                    publisher_ids_for_short_link.append(pub_id)
        
        try:
            await self.db.commit()
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
            # 导入短链接同步函数
            from app.api.api_v1.endpoints.cpl.offers import sync_short_links_for_offer
            short_link_info = await sync_short_links_for_offer(
                db=self.db,
                offer_id=offer.id,
                publisher_ids=publisher_ids_for_short_link,
                offer_name=offer.offer_name,
                base_url=base_url,
                current_user_id=current_user.id,
                advertiser_tracklink=offer.advertiser_tracklink
            )
            await self.db.commit()  # 提交短链接创建
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
        更新Offer信息（支持渠道分配更新和短链接同步）
        
        Args:
            offer_id: Offer ID
            offer_data: 更新的数据字典（可能包含publisher_configs或publisher_ids）
            current_user: 当前用户
        
        Returns:
            Tuple[Offer, Optional[Dict], Optional[Dict], bool]: 
            (更新后的Offer对象, 短链接信息, 下游Tracklink短链接信息, downstream_tracklink是否改变)
        """
        # 权限检查
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
        
        # 检查advertiser_tracklink是否改变
        advertiser_tracklink_changed = False
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
        publisher_ids = offer_data.get('publisher_ids')
        
        if publisher_configs is not None:
            # 使用新的渠道配置方式
            # 获取旧的渠道分配列表（用于比较）
            old_assignments_result = await self.db.execute(
                select(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
            )
            old_assignments = old_assignments_result.scalars().all()
            old_publisher_ids = {assignment.publisher_id for assignment in old_assignments}
            
            # 先删除所有现有分配
            await self.db.execute(
                delete(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
            )
            
            # 添加新分配
            if len(publisher_configs) == 0:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="渠道配置不能为空，请至少添加一个渠道"
                )
            
            # 验证是否有重复的publisher_id（先过滤None值，因为None会在后面单独验证）
            publisher_id_list = [
                config.get('publisher_id') if isinstance(config, dict) else config.publisher_id 
                for config in publisher_configs
            ]
            # 过滤掉None值，因为None会在后面单独验证
            valid_publisher_ids = [pid for pid in publisher_id_list if pid is not None]
            if len(valid_publisher_ids) != len(set(valid_publisher_ids)):
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="渠道配置中存在重复的渠道ID"
                )
            
            for config in publisher_configs:
                # 处理字典或对象
                if isinstance(config, dict):
                    pub_id = config.get('publisher_id')
                    downstream_cap = config.get('downstream_cap')
                    affiliate_payout = config.get('affiliate_payout')
                else:
                    pub_id = config.publisher_id
                    downstream_cap = config.downstream_cap
                    affiliate_payout = config.affiliate_payout
                
                # 验证publisher_id是否存在且有效
                if pub_id is None:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail="渠道配置中的publisher_id不能为空，请确保已选择渠道"
                    )
                
                # 验证publisher_id类型（必须是整数）
                try:
                    pub_id = int(pub_id)
                except (ValueError, TypeError):
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail=f"渠道配置中的publisher_id必须是整数，当前值: {pub_id} (类型: {type(pub_id).__name__})"
                    )
                
                # 验证publisher_id范围（必须大于0）
                if pub_id <= 0:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail=f"渠道配置中的publisher_id必须大于0，当前值: {pub_id}"
                    )
                
                # 验证downstream_cap和affiliate_payout不能为负数
                # 同时验证类型（downstream_cap必须是整数或None，affiliate_payout必须是浮点数或None）
                if downstream_cap is not None:
                    try:
                        downstream_cap = int(downstream_cap)
                    except (ValueError, TypeError):
                        raise_api_exception(
                            ErrorCode.INVALID_PARAMETER,
                            detail=f"渠道ID {pub_id} 的下游Cap必须是整数，当前值: {downstream_cap} (类型: {type(downstream_cap).__name__})"
                        )
                
                if affiliate_payout is not None:
                    try:
                        affiliate_payout = float(affiliate_payout)
                    except (ValueError, TypeError):
                        raise_api_exception(
                            ErrorCode.INVALID_PARAMETER,
                            detail=f"渠道ID {pub_id} 的下游PO必须是数字，当前值: {affiliate_payout} (类型: {type(affiliate_payout).__name__})"
                        )
                
                # 验证downstream_cap和affiliate_payout不能为负数
                if downstream_cap is not None and downstream_cap < 0:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail=f"渠道ID {pub_id} 的下游Cap不能为负数"
                    )
                
                if affiliate_payout is not None and affiliate_payout < 0:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMETER,
                        detail=f"渠道ID {pub_id} 的下游PO不能为负数"
                    )
                
                # 验证渠道是否存在
                pub_result = await self.db.execute(
                    select(Publisher).where(Publisher.id == pub_id)
                )
                publisher = pub_result.scalar_one_or_none()
                if not publisher:
                    raise_api_exception(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        detail=f"渠道ID {pub_id} 不存在"
                    )
                
                assignment = OfferPublisherAssignment(
                    offer_id=offer.id,
                    publisher_id=pub_id,
                    downstream_cap=downstream_cap,
                    affiliate_payout=affiliate_payout,
                    is_active=True
                )
                self.db.add(assignment)
                publisher_ids_for_short_link.append(pub_id)
        elif publisher_ids is not None:
            # 向后兼容：使用旧的publisher_ids方式
            # 获取旧的渠道分配列表（用于比较）
            old_assignments_result = await self.db.execute(
                select(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
            )
            old_assignments = old_assignments_result.scalars().all()
            old_publisher_ids = {assignment.publisher_id for assignment in old_assignments}
            
            # 先删除所有现有分配
            await self.db.execute(
                delete(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
            )
            
            # 添加新分配
            if publisher_ids:
                for pub_id in publisher_ids:
                    pub_result = await self.db.execute(
                        select(Publisher).where(Publisher.id == pub_id)
                    )
                    publisher = pub_result.scalar_one_or_none()
                    if publisher:
                        assignment = OfferPublisherAssignment(
                            offer_id=offer.id,
                            publisher_id=pub_id,
                            is_active=True
                    )
                    self.db.add(assignment)
                    publisher_ids_for_short_link.append(pub_id)
        
        try:
            await self.db.commit()
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
        
        # 如果advertiser_tracklink改变了，删除该Offer的所有旧短链接
        if advertiser_tracklink_changed:
            old_short_links_result = await self.db.execute(
                select(ShortLink).where(ShortLink.offer_id == offer_id)
            )
            old_short_links = old_short_links_result.scalars().all()
            
            if old_short_links:
                deleted_count = 0
                for old_link in old_short_links:
                    await self.db.execute(
                        delete(ShortLink).where(ShortLink.id == old_link.id)
                    )
                    deleted_count += 1
                logger.info(
                    f"删除旧的短链接（advertiser_tracklink已改变）: "
                    f"offer_id={offer_id}, "
                    f"deleted_count={deleted_count}, "
                    f"old_advertiser_tracklink={old_advertiser_tracklink}"
                )
                await self.db.commit()
        
        # 如果渠道分配有变化或advertiser_tracklink改变，同步短链接
        short_link_info = None
        need_sync_short_links = False
        
        # 检查是否需要同步短链接
        if publisher_configs is not None:
            new_publisher_ids = set(publisher_ids_for_short_link)
            if old_publisher_ids != new_publisher_ids:
                need_sync_short_links = True
        elif publisher_ids is not None:
            new_publisher_ids = set(publisher_ids or [])
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
            elif publisher_ids is not None:
                current_publisher_ids = publisher_ids
            else:
                # 如果没有明确指定publisher_ids，使用现有的分配
                existing_assignments_result = await self.db.execute(
                    select(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
                )
                existing_assignments = existing_assignments_result.scalars().all()
                current_publisher_ids = [assignment.publisher_id for assignment in existing_assignments]
            
            if current_advertiser_tracklink and current_publisher_ids:
                from app.core.config import settings
                from app.api.api_v1.endpoints.cpl.offers import sync_short_links_for_offer
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
                await self.db.commit()  # 提交短链接变更
                await self.db.refresh(offer)
            elif not current_advertiser_tracklink:
                logger.warning(f"Offer {offer.id} 没有配置上游Tracklink，无法创建短链接")
        
        # 检查下游Tracklink是否在short_links表中存在，如果不存在则创建
        downstream_tracklink_short_link_info = None
        current_downstream_tracklink = offer.downstream_tracklink
        current_advertiser_tracklink = offer.advertiser_tracklink
        if current_downstream_tracklink and current_advertiser_tracklink:
            from app.core.config import settings
            from app.api.api_v1.endpoints.cpl.offers import (
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
                    await self.db.commit()
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
        删除Offer
        
        Args:
            offer_id: Offer ID
            current_user: 当前用户
        """
        # 权限检查
        self.require_admin(current_user)
        
        # 获取Offer
        offer = await self.get_offer_by_id(offer_id, current_user, include_advertiser=False)
        
        # 检查是否有关联的点击记录
        from app.models.models import Click
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
        await self.db.commit()
        
        logger.info(f"Offer已删除: {offer.offer_name} (ID: {offer_id})")

