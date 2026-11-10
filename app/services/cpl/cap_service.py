"""
Cap（转化上限）服务层。

功能说明：
- Offer/渠道维度日 Cap 配置 CRUD 与当前计数查询
- 与 ``app.core.cap`` 计数器及每日重置定时任务配合

在系统中的位置：
- 被管理端 Cap 管理 API 调用

注意事项：
1. Cap 归零由 ``cpl_tasks.reset_daily_caps`` 在 UTC 0 点执行
2. 修改 Cap 配置后应同步 Redis/内存计数状态（如有缓存）
"""
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.utils import get_app_now_naive
from app.models.models import OfferCap, Offer, Publisher, User
from app.schemas.cpl.cap import OfferCapResponse
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)


class CapService(BaseService[OfferCap]):
    """
    Cap 配置业务服务。

    管理 Offer 维度的日 Cap / 总 Cap 及当前计数。
    cap_type 区分全局、广告主-Offer、渠道等粒度。
    """

    def __init__(self, db: AsyncSession):
        """注入异步数据库会话。"""
        super().__init__(db, OfferCap)

    async def _validate_cap_scope(
        self,
        scope: Dict[str, Any],
        *,
        exclude_cap_id: Optional[int] = None,
    ) -> Offer:
        """校验 Cap 归属与唯一业务范围，并锁定 Offer 串行化同一 Offer 的配置写入。

        Offer 行锁让通过本服务创建/更新同一 Offer 的并发请求串行执行；
        不能用可空列的普通复合唯一索引替代，因为 MySQL UNIQUE 允许多个 NULL。
        """
        cap_type = scope.get("cap_type")
        if cap_type not in {"offer", "advertiser_offer"}:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="Cap 类型只能是 offer 或 advertiser_offer",
            )

        offer_id = scope.get("offer_id")
        offer_result = await self.db.execute(
            select(Offer).where(Offer.id == offer_id).with_for_update()
        )
        offer = offer_result.scalars().first()
        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {offer_id} 不存在",
            )

        advertiser_id = scope.get("advertiser_id")
        if cap_type == "advertiser_offer":
            if advertiser_id is None or advertiser_id != offer.advertiser_id:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="广告主专属 Cap 的 advertiser_id 必须与 Offer 所属广告主一致",
                )
        elif advertiser_id is not None:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="Offer 全局 Cap 不允许设置 advertiser_id",
            )

        publisher_id = scope.get("publisher_id")
        if publisher_id is not None:
            publisher_result = await self.db.execute(
                select(Publisher.id).where(Publisher.id == publisher_id).limit(1)
            )
            if publisher_result.scalar_one_or_none() is None:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"渠道ID {publisher_id} 不存在",
                )

        duplicate_filters = [
            OfferCap.cap_type == cap_type,
            OfferCap.advertiser_id == advertiser_id,
            OfferCap.offer_id == offer_id,
            OfferCap.publisher_id == publisher_id,
        ]
        if exclude_cap_id is not None:
            duplicate_filters.append(OfferCap.id != exclude_cap_id)
        duplicate_result = await self.db.execute(
            select(OfferCap.id).where(*duplicate_filters).limit(1)
        )
        if duplicate_result.scalar_one_or_none() is not None:
            raise_api_exception(
                ErrorCode.RESOURCE_ALREADY_EXISTS,
                detail="相同 Offer、广告主、渠道和 Cap 类型的配置已存在",
            )

        return offer

    @staticmethod
    def to_cap_response(cap: OfferCap) -> OfferCapResponse:
        """
        将 ORM 实体转为 API 响应 Schema，并填充关联名称。

        Args:
            cap: 已预加载 offer/advertiser/publisher 的 OfferCap

        Returns:
            OfferCapResponse: 含 offer_name、advertiser_name、publisher_name
        """
        cap_data = OfferCapResponse.model_validate(cap)
        cap_data.offer_name = cap.offer.offer_name if cap.offer else None
        cap_data.advertiser_name = (
            cap.advertiser.advertiser_name if cap.advertiser else None
        )
        cap_data.publisher_name = (
            cap.publisher.publisher_name if cap.publisher else None
        )
        return cap_data

    def to_cap_response_list(self, caps: List[OfferCap]) -> List[OfferCapResponse]:
        """
        批量转换 Cap 列表为响应 Schema。

        Args:
            caps: OfferCap 实体列表

        Returns:
            List[OfferCapResponse]: 与输入顺序一致的响应列表
        """
        return [self.to_cap_response(cap) for cap in caps]

    async def check_cap_consistency(
            self,
            offer_id: Optional[int] = None,
            fix: bool = False,
    ) -> tuple[list, str]:
        """
        检查 Cap 当前计数与真实转化数是否一致。

        Args:
            offer_id: 限定单个 Offer，None 表示全量扫描
            fix: 兼容旧 API 参数；为保护并发预留，不再执行 DB -> Redis 自动覆盖

        Returns:
            tuple[list, str]: (不一致记录列表, 人类可读摘要信息)
        """
        from app.core.cap.consistency_checker import check_cap_consistency

        inconsistencies = await check_cap_consistency(
            db=self.db,
            offer_id=offer_id,
            fix_inconsistencies=fix,
        )
        if inconsistencies:
            message = f"发现 {len(inconsistencies)} 个不一致的记录"
            if fix:
                message += "；自动覆盖修复已禁用，需通过安全同步流程处理"
        else:
            message = "所有Cap计数一致"
        return inconsistencies, message

    async def create_cap(
            self,
            cap_data: Dict[str, Any],
            current_user: User
    ) -> OfferCap:
        """
        创建 Cap 配置。

        校验 Offer 必存在；advertiser_offer 类型需校验广告主；
        指定 publisher_id 时校验渠道。设置 total_cap 时自动写入 cap_start_date。

        Args:
            cap_data: 含 cap_type、offer_id 及可选 daily_cap、total_cap 等
            current_user: 当前操作用户（审计预留）

        Returns:
            OfferCap: 创建成功并已 joinedload 关联实体的对象

        Raises:
            APIException: 关联实体不存在或数据库写入失败
        """
        # 锁定 Offer 并校验广告主归属、渠道及重复配置。
        await self._validate_cap_scope(cap_data)

        # 设置Cap开始日期（用于Total Cap）
        cap_start_date = None
        if cap_data.get('total_cap'):
            cap_start_date = get_app_now_naive()  # 使用北京时间

        cap = OfferCap(
            cap_type=cap_data['cap_type'],
            advertiser_id=cap_data.get('advertiser_id'),
            offer_id=cap_data['offer_id'],
            publisher_id=cap_data.get('publisher_id'),
            daily_cap=cap_data.get('daily_cap'),
            total_cap=cap_data.get('total_cap'),
            current_daily_count=0,
            current_total_count=0,
            cap_start_date=cap_start_date,
            is_active=cap_data.get('is_active', True)
        )

        try:
            self.db.add(cap)
            await self.db.flush()
            await self.db.refresh(cap)

            # 重新加载关联信息（使用joinedload优化）
            query = select(OfferCap).where(OfferCap.id == cap.id).options(
                joinedload(OfferCap.offer),
                joinedload(OfferCap.advertiser),
                joinedload(OfferCap.publisher)
            )
            result = await self.db.execute(query)
            # 使用joinedload时，为了安全起见使用unique()去重
            cap = result.unique().scalars().first()

            logger.info(f"Cap配置创建成功: cap_id={cap.id}")
            return cap
        except Exception as e:
            await self.db.rollback()
            logger.error(f"创建Cap配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"创建Cap配置失败: {str(e)}"
            )

    async def get_caps(
            self,
            page: int = 1,
            page_size: int = 20,
            cap_type: Optional[str] = None,
            offer_id: Optional[int] = None,
            advertiser_id: Optional[int] = None,
            publisher_id: Optional[int] = None,
            is_active: Optional[bool] = None
    ) -> tuple[List[OfferCap], int]:
        """
        分页查询 Cap 配置列表。

        支持多维度过滤，结果按创建时间倒序，预加载 Offer/广告主/渠道。

        Args:
            page: 页码，从 1 开始
            page_size: 每页条数
            cap_type: Cap 粒度类型过滤
            offer_id: 按 Offer 过滤
            advertiser_id: 按广告主过滤
            publisher_id: 按渠道过滤
            is_active: 激活状态过滤

        Returns:
            tuple[List[OfferCap], int]: (当前页列表, 总条数)
        """
        query = select(OfferCap)

        if cap_type:
            query = query.where(OfferCap.cap_type == cap_type)

        if offer_id:
            query = query.where(OfferCap.offer_id == offer_id)

        if advertiser_id:
            query = query.where(OfferCap.advertiser_id == advertiser_id)

        if publisher_id:
            query = query.where(OfferCap.publisher_id == publisher_id)

        if is_active is not None:
            query = query.where(OfferCap.is_active == is_active)

        # 总数
        total_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(OfferCap.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        # 使用joinedload优化关联查询，减少N+1查询问题
        query = query.options(
            joinedload(OfferCap.offer),
            joinedload(OfferCap.advertiser),
            joinedload(OfferCap.publisher)
        )
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        caps = result.unique().scalars().all()

        return caps, total

    async def get_cap_by_id(self, cap_id: int) -> Optional[OfferCap]:
        """
        按主键获取 Cap 详情（含关联名称所需的外键实体）。

        Args:
            cap_id: Cap 配置主键

        Returns:
            Optional[OfferCap]: 存在则返回预加载关联的实体，否则 None
        """
        # 使用joinedload优化关联查询
        query = select(OfferCap).where(OfferCap.id == cap_id).options(
            joinedload(OfferCap.offer),
            joinedload(OfferCap.advertiser),
            joinedload(OfferCap.publisher)
        )
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        return result.unique().scalars().first()

    async def update_cap(
            self,
            cap_id: int,
            update_data: Dict[str, Any],
            current_user: User
    ) -> OfferCap:
        """
        更新 Cap 配置。

        首次设置 total_cap 且尚无 cap_start_date 时，自动补写开始日期。

        Args:
            cap_id: Cap 配置主键
            update_data: 待更新字段字典，仅模型存在的属性会被 setattr
            current_user: 当前操作用户

        Returns:
            OfferCap: 更新后并重新 joinedload 的实体

        Raises:
            APIException: 记录不存在或提交失败
        """
        result = await self.db.execute(
            select(OfferCap).where(OfferCap.id == cap_id).with_for_update()
        )
        cap = result.scalars().first()

        if not cap:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Cap配置ID {cap_id} 不存在"
            )

        # 先合并现有范围与更新字段，再执行与创建相同的完整校验。
        effective_scope = {
            "cap_type": cap.cap_type,
            "advertiser_id": cap.advertiser_id,
            "offer_id": cap.offer_id,
            "publisher_id": cap.publisher_id,
        }
        effective_scope.update({
            key: update_data[key]
            for key in ("cap_type", "advertiser_id", "offer_id", "publisher_id")
            if key in update_data
        })
        await self._validate_cap_scope(
            effective_scope,
            exclude_cap_id=cap_id,
        )

        # 如果首次设置 total_cap 且尚无 cap_start_date，设置开始日期。
        if 'total_cap' in update_data and update_data['total_cap'] and not cap.cap_start_date:
            update_data['cap_start_date'] = get_app_now_naive()  # 使用北京时间

        for key, value in update_data.items():
            if hasattr(cap, key):
                setattr(cap, key, value)

        try:
            await self.db.flush()
            await self.db.refresh(cap)

            # 重新加载关联信息（使用joinedload优化）
            query = select(OfferCap).where(OfferCap.id == cap.id).options(
                joinedload(OfferCap.offer),
                joinedload(OfferCap.advertiser),
                joinedload(OfferCap.publisher)
            )
            result = await self.db.execute(query)
            # 使用joinedload时，为了安全起见使用unique()去重
            cap = result.unique().scalars().first()

            logger.info(f"Cap配置更新成功: cap_id={cap_id}")
            return cap
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新Cap配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新Cap配置失败: {str(e)}"
            )

    async def delete_cap(
            self,
            cap_id: int,
            current_user: User
    ) -> None:
        """
        物理删除 Cap 配置。

        Args:
            cap_id: Cap 配置主键
            current_user: 当前操作用户

        Raises:
            APIException: 记录不存在或删除失败
        """
        result = await self.db.execute(
            select(OfferCap).where(OfferCap.id == cap_id)
        )
        cap = result.scalars().first()

        if not cap:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Cap配置ID {cap_id} 不存在"
            )

        try:
            await self.db.execute(delete(OfferCap).where(OfferCap.id == cap_id))
            await self.db.flush()

            logger.info(f"Cap配置删除成功: cap_id={cap_id}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除Cap配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除Cap配置失败: {str(e)}"
            )
