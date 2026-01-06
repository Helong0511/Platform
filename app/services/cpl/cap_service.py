"""
Cap 管理服务层
封装Cap配置的业务逻辑
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.models.models import OfferCap, Offer, Advertiser, Publisher, User
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import get_app_now_naive
import logging

logger = logging.getLogger(__name__)


class CapService(BaseService[OfferCap]):
    """Cap配置服务"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, OfferCap)

    async def create_cap(
        self,
        cap_data: Dict[str, Any],
        current_user: User
    ) -> OfferCap:
        """
        创建Cap配置

        Args:
            cap_data: Cap配置数据
            current_user: 当前用户

        Returns:
            OfferCap: 创建的Cap配置对象
        """
        # 验证Offer是否存在
        offer_result = await self.db.execute(
            select(Offer).where(Offer.id == cap_data['offer_id'])
        )
        offer = offer_result.scalars().first()
        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {cap_data['offer_id']} 不存在"
            )

        # 如果是advertiser_offer类型，验证广告主
        if cap_data.get('cap_type') == 'advertiser_offer' and cap_data.get('advertiser_id'):
            adv_result = await self.db.execute(
                select(Advertiser).where(Advertiser.id == cap_data['advertiser_id'])
            )
            advertiser = adv_result.scalars().first()
            if not advertiser:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"广告主ID {cap_data['advertiser_id']} 不存在"
                )

        # 如果指定了渠道，验证渠道
        if cap_data.get('publisher_id'):
            pub_result = await self.db.execute(
                select(Publisher).where(Publisher.id == cap_data['publisher_id'])
            )
            publisher = pub_result.scalars().first()
            if not publisher:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"渠道ID {cap_data['publisher_id']} 不存在"
                )

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
            await self.db.commit()
            await self.db.refresh(cap)

            # 重新加载关联信息（使用joinedload优化）
            query = select(OfferCap).where(OfferCap.id == cap.id).options(
                joinedload(OfferCap.offer),
                joinedload(OfferCap.advertiser),
                joinedload(OfferCap.publisher)
            )
            result = await self.db.execute(query)
            cap = result.scalars().first()

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
        获取Cap配置列表

        Args:
            page: 页码
            page_size: 每页数量
            cap_type: Cap类型过滤
            offer_id: Offer ID过滤
            advertiser_id: 广告主ID过滤
            publisher_id: 渠道ID过滤
            is_active: 是否激活过滤

        Returns:
            tuple[List[OfferCap], int]: (Cap配置列表, 总数)
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
        caps = result.scalars().all()

        return caps, total

    async def get_cap_by_id(self, cap_id: int) -> Optional[OfferCap]:
        """
        根据ID获取Cap配置详情

        Args:
            cap_id: Cap配置ID

        Returns:
            Optional[OfferCap]: Cap配置对象，如果不存在则返回None
        """
        # 使用joinedload优化关联查询
        query = select(OfferCap).where(OfferCap.id == cap_id).options(
            joinedload(OfferCap.offer),
            joinedload(OfferCap.advertiser),
            joinedload(OfferCap.publisher)
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_cap(
        self,
        cap_id: int,
        update_data: Dict[str, Any],
        current_user: User
    ) -> OfferCap:
        """
        更新Cap配置

        Args:
            cap_id: Cap配置ID
            update_data: 更新数据
            current_user: 当前用户

        Returns:
            OfferCap: 更新后的Cap配置对象
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

        # 如果更新了total_cap且之前没有cap_start_date，设置开始日期
        if 'total_cap' in update_data and update_data['total_cap'] and not cap.cap_start_date:
            update_data['cap_start_date'] = get_app_now_naive()  # 使用北京时间

        for key, value in update_data.items():
            if hasattr(cap, key):
                setattr(cap, key, value)

        try:
            await self.db.commit()
            await self.db.refresh(cap)

            # 重新加载关联信息（使用joinedload优化）
            query = select(OfferCap).where(OfferCap.id == cap.id).options(
                joinedload(OfferCap.offer),
                joinedload(OfferCap.advertiser),
                joinedload(OfferCap.publisher)
            )
            result = await self.db.execute(query)
            cap = result.scalars().first()

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
        删除Cap配置

        Args:
            cap_id: Cap配置ID
            current_user: 当前用户
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
            from sqlalchemy import delete
            await self.db.execute(delete(OfferCap).where(OfferCap.id == cap_id))
            await self.db.commit()

            logger.info(f"Cap配置删除成功: cap_id={cap_id}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除Cap配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除Cap配置失败: {str(e)}"
            )

