"""
Discount 管理服务层
封装扣量配置的业务逻辑
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.models.models import OfferDiscount, Offer, Publisher, User
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
import logging

logger = logging.getLogger(__name__)


class DiscountService(BaseService[OfferDiscount]):
    """扣量配置服务"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, OfferDiscount)

    async def create_discount(
        self,
        discount_data: Dict[str, Any],
        current_user: User
    ) -> OfferDiscount:
        """
        创建扣量配置

        Args:
            discount_data: 扣量配置数据
            current_user: 当前用户

        Returns:
            OfferDiscount: 创建的扣量配置对象
        """
        # 验证渠道是否存在
        pub_result = await self.db.execute(
            select(Publisher).where(Publisher.id == discount_data['publisher_id'])
        )
        publisher = pub_result.scalars().first()
        if not publisher:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {discount_data['publisher_id']} 不存在"
            )

        # 如果是offer类型，验证Offer
        if discount_data.get('discount_type') == 'offer' and discount_data.get('offer_id'):
            offer_result = await self.db.execute(
                select(Offer).where(Offer.id == discount_data['offer_id'])
            )
            offer = offer_result.scalars().first()
            if not offer:
                raise_api_exception(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    detail=f"Offer ID {discount_data['offer_id']} 不存在"
                )

        discount = OfferDiscount(
            discount_type=discount_data['discount_type'],
            offer_id=discount_data.get('offer_id'),
            publisher_id=discount_data['publisher_id'],
            discount_ratio=discount_data['discount_ratio'],
            is_active=discount_data.get('is_active', True)
        )

        try:
            self.db.add(discount)
            await self.db.commit()
            await self.db.refresh(discount)

            # 重新加载关联信息（使用joinedload优化）
            query = select(OfferDiscount).where(OfferDiscount.id == discount.id).options(
                joinedload(OfferDiscount.publisher),
                joinedload(OfferDiscount.offer)
            )
            result = await self.db.execute(query)
            discount = result.scalars().first()

            logger.info(f"扣量配置创建成功: discount_id={discount.id}")
            return discount
        except Exception as e:
            await self.db.rollback()
            logger.error(f"创建扣量配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"创建扣量配置失败: {str(e)}"
            )

    async def get_discounts(
        self,
        page: int = 1,
        page_size: int = 20,
        discount_type: Optional[str] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        is_active: Optional[bool] = None
    ) -> tuple[List[OfferDiscount], int]:
        """
        获取扣量配置列表

        Args:
            page: 页码
            page_size: 每页数量
            discount_type: 扣量类型过滤
            offer_id: Offer ID过滤
            publisher_id: 渠道ID过滤
            is_active: 是否激活过滤

        Returns:
            tuple[List[OfferDiscount], int]: (扣量配置列表, 总数)
        """
        query = select(OfferDiscount)

        if discount_type:
            query = query.where(OfferDiscount.discount_type == discount_type)

        if offer_id:
            query = query.where(OfferDiscount.offer_id == offer_id)

        if publisher_id:
            query = query.where(OfferDiscount.publisher_id == publisher_id)

        if is_active is not None:
            query = query.where(OfferDiscount.is_active == is_active)

        # 总数
        total_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(OfferDiscount.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        # 使用joinedload优化关联查询，减少N+1查询问题
        query = query.options(
            joinedload(OfferDiscount.publisher),
            joinedload(OfferDiscount.offer)
        )
        result = await self.db.execute(query)
        discounts = result.scalars().all()

        return discounts, total

    async def get_discount_by_id(self, discount_id: int) -> Optional[OfferDiscount]:
        """
        根据ID获取扣量配置详情

        Args:
            discount_id: 扣量配置ID

        Returns:
            Optional[OfferDiscount]: 扣量配置对象，如果不存在则返回None
        """
        # 使用joinedload优化关联查询
        query = select(OfferDiscount).where(OfferDiscount.id == discount_id).options(
            joinedload(OfferDiscount.publisher),
            joinedload(OfferDiscount.offer)
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_discount(
        self,
        discount_id: int,
        update_data: Dict[str, Any],
        current_user: User
    ) -> OfferDiscount:
        """
        更新扣量配置

        Args:
            discount_id: 扣量配置ID
            update_data: 更新数据
            current_user: 当前用户

        Returns:
            OfferDiscount: 更新后的扣量配置对象
        """
        result = await self.db.execute(
            select(OfferDiscount).where(OfferDiscount.id == discount_id)
        )
        discount = result.scalars().first()

        if not discount:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"扣量配置ID {discount_id} 不存在"
            )

        for key, value in update_data.items():
            if hasattr(discount, key):
                setattr(discount, key, value)

        try:
            await self.db.commit()
            await self.db.refresh(discount)

            # 重新加载关联信息（使用joinedload优化）
            query = select(OfferDiscount).where(OfferDiscount.id == discount.id).options(
                joinedload(OfferDiscount.publisher),
                joinedload(OfferDiscount.offer)
            )
            result = await self.db.execute(query)
            discount = result.scalars().first()

            logger.info(f"扣量配置更新成功: discount_id={discount_id}")
            return discount
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新扣量配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新扣量配置失败: {str(e)}"
            )

    async def delete_discount(
        self,
        discount_id: int,
        current_user: User
    ) -> None:
        """
        删除扣量配置

        Args:
            discount_id: 扣量配置ID
            current_user: 当前用户
        """
        result = await self.db.execute(
            select(OfferDiscount).where(OfferDiscount.id == discount_id)
        )
        discount = result.scalars().first()

        if not discount:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"扣量配置ID {discount_id} 不存在"
            )

        try:
            from sqlalchemy import delete
            await self.db.execute(delete(OfferDiscount).where(OfferDiscount.id == discount_id))
            await self.db.commit()

            logger.info(f"扣量配置删除成功: discount_id={discount_id}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除扣量配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除扣量配置失败: {str(e)}"
            )

