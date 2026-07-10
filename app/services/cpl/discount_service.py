"""
折扣配置服务层。

功能说明：
- 管理 Offer/渠道折扣规则，影响结算金额与报表展示
- 校验折扣区间、生效时间与互斥关系

在系统中的位置：
- 被管理端折扣 API 调用

注意事项：
1. 折扣变更不追溯历史转化，仅影响新入库数据计算
2. 删除折扣前确认无进行中的结算依赖
"""
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.models.models import OfferDiscount, Offer, Publisher, User
from app.schemas.cpl.discount import OfferDiscountResponse
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)


class DiscountService(BaseService[OfferDiscount]):
    """
    扣量配置业务服务。

    discount_type 区分全局渠道扣量或单 Offer 级扣量；
    discount_ratio 表示扣减比例，影响转化 payout 计算。
    """

    def __init__(self, db: AsyncSession):
        """注入异步数据库会话。"""
        super().__init__(db, OfferDiscount)

    @staticmethod
    def to_discount_response(discount: OfferDiscount) -> OfferDiscountResponse:
        """
        将 ORM 实体转为 API 响应 Schema，并填充关联名称。

        Args:
            discount: 已预加载 publisher/offer 的 OfferDiscount

        Returns:
            OfferDiscountResponse: 含 publisher_name、offer_name
        """
        discount_data = OfferDiscountResponse.model_validate(discount)
        discount_data.publisher_name = (
            discount.publisher.publisher_name if discount.publisher else None
        )
        discount_data.offer_name = discount.offer.offer_name if discount.offer else None
        return discount_data

    def to_discount_response_list(
            self, discounts: List[OfferDiscount]
    ) -> List[OfferDiscountResponse]:
        """
        批量转换扣量配置列表为响应 Schema。

        Args:
            discounts: OfferDiscount 实体列表

        Returns:
            List[OfferDiscountResponse]: 与输入顺序一致的响应列表
        """
        return [self.to_discount_response(d) for d in discounts]

    async def create_discount(
            self,
            discount_data: Dict[str, Any],
            current_user: User
    ) -> OfferDiscount:
        """
        创建扣量配置。

        publisher_id 必填且须存在；discount_type 为 offer 时 offer_id 须有效。

        Args:
            discount_data: 含 discount_type、publisher_id、discount_ratio 等
            current_user: 当前操作用户

        Returns:
            OfferDiscount: 创建成功并已 joinedload 关联实体的对象

        Raises:
            APIException: 关联实体不存在或写入失败
        """
        # --- 关联实体校验 ---
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
            await self.db.flush()
            await self.db.refresh(discount)

            # 重新加载关联信息（使用joinedload优化）
            query = select(OfferDiscount).where(OfferDiscount.id == discount.id).options(
                joinedload(OfferDiscount.publisher),
                joinedload(OfferDiscount.offer)
            )
            result = await self.db.execute(query)
            # 使用joinedload时，为了安全起见使用unique()去重
            discount = result.unique().scalars().first()

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
        分页查询扣量配置列表。

        Args:
            page: 页码，从 1 开始
            page_size: 每页条数
            discount_type: 扣量粒度类型过滤
            offer_id: 按 Offer 过滤
            publisher_id: 按渠道过滤
            is_active: 激活状态过滤

        Returns:
            tuple[List[OfferDiscount], int]: (当前页列表, 总条数)
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
        # 使用joinedload时，为了安全起见使用unique()去重
        discounts = result.unique().scalars().all()

        return discounts, total

    async def get_discount_by_id(self, discount_id: int) -> Optional[OfferDiscount]:
        """
        按主键获取扣量配置详情（含渠道与 Offer 关联）。

        Args:
            discount_id: 扣量配置主键

        Returns:
            Optional[OfferDiscount]: 存在则返回预加载关联的实体，否则 None
        """
        # 使用joinedload优化关联查询
        query = select(OfferDiscount).where(OfferDiscount.id == discount_id).options(
            joinedload(OfferDiscount.publisher),
            joinedload(OfferDiscount.offer)
        )
        result = await self.db.execute(query)
        # 使用joinedload时，为了安全起见使用unique()去重
        return result.unique().scalars().first()

    async def update_discount(
            self,
            discount_id: int,
            update_data: Dict[str, Any],
            current_user: User
    ) -> OfferDiscount:
        """
        更新扣量配置。

        Args:
            discount_id: 扣量配置主键
            update_data: 待更新字段字典
            current_user: 当前操作用户

        Returns:
            OfferDiscount: 更新后并重新 joinedload 的实体

        Raises:
            APIException: 记录不存在或提交失败
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
            await self.db.flush()
            await self.db.refresh(discount)

            # 重新加载关联信息（使用joinedload优化）
            query = select(OfferDiscount).where(OfferDiscount.id == discount.id).options(
                joinedload(OfferDiscount.publisher),
                joinedload(OfferDiscount.offer)
            )
            result = await self.db.execute(query)
            # 使用joinedload时，为了安全起见使用unique()去重
            discount = result.unique().scalars().first()

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
        物理删除扣量配置。

        Args:
            discount_id: 扣量配置主键
            current_user: 当前操作用户

        Raises:
            APIException: 记录不存在或删除失败
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
            await self.db.execute(delete(OfferDiscount).where(OfferDiscount.id == discount_id))
            await self.db.flush()

            logger.info(f"扣量配置删除成功: discount_id={discount_id}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除扣量配置失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除扣量配置失败: {str(e)}"
            )
