"""
扣量管理逻辑
用于计算扣量和处理优先级
"""
import logging
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_

from app.models.models import OfferDiscount, Offer, Publisher

logger = logging.getLogger(__name__)


async def calculate_discount(
    db: AsyncSession,
    offer_id: int,
    publisher_id: int,
    original_payout: float
) -> Tuple[float, float, Optional[str]]:
    """
    计算扣量后的金额
    
    优先级：offer级别 > channel级别
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        publisher_id: 渠道ID
        original_payout: 原始支付金额
        
    Returns:
        (扣量后金额, 扣量金额, 扣量类型说明)
    """
    try:
        # 1. 优先查找 offer 级别的扣量配置
        offer_discount_result = await db.execute(
            select(OfferDiscount).where(
                and_(
                    OfferDiscount.discount_type == 'offer',
                    OfferDiscount.offer_id == offer_id,
                    OfferDiscount.publisher_id == publisher_id,
                    OfferDiscount.is_active == True
                )
            )
        )
        offer_discount = offer_discount_result.scalars().first()
        
        if offer_discount:
            discount_ratio = offer_discount.discount_ratio
            discount_amount = original_payout * (discount_ratio / 100)
            final_payout = original_payout - discount_amount
            return final_payout, discount_amount, f"Offer级别扣量: {discount_ratio}%"
        
        # 2. 如果没有 offer 级别，查找 channel 级别的扣量配置
        channel_discount_result = await db.execute(
            select(OfferDiscount).where(
                and_(
                    OfferDiscount.discount_type == 'channel',
                    OfferDiscount.publisher_id == publisher_id,
                    OfferDiscount.is_active == True
                )
            )
        )
        channel_discount = channel_discount_result.scalars().first()
        
        if channel_discount:
            discount_ratio = channel_discount.discount_ratio
            discount_amount = original_payout * (discount_ratio / 100)
            final_payout = original_payout - discount_amount
            return final_payout, discount_amount, f"Channel级别扣量: {discount_ratio}%"
        
        # 3. 检查渠道级别的默认扣量（Publisher 表的 price_discount 字段）
        publisher_result = await db.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        publisher = publisher_result.scalars().first()
        
        if publisher and publisher.price_discount and publisher.price_discount > 0:
            discount_ratio = publisher.price_discount
            discount_amount = original_payout * (discount_ratio / 100)
            final_payout = original_payout - discount_amount
            return final_payout, discount_amount, f"渠道默认扣量: {discount_ratio}%"
        
        # 4. 没有扣量配置，返回原始金额
        return original_payout, 0.0, None
        
    except Exception as e:
        logger.error(f"计算扣量失败: {str(e)}", exc_info=True)
        # 出错时返回原始金额，避免影响正常流程
        return original_payout, 0.0, None


async def get_discount_info(
    db: AsyncSession,
    offer_id: int,
    publisher_id: int
) -> Optional[dict]:
    """
    获取扣量信息（不计算，仅查询配置）
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        publisher_id: 渠道ID
        
    Returns:
        扣量信息字典，包含 discount_type, discount_ratio, description
    """
    try:
        # 优先查找 offer 级别
        offer_discount_result = await db.execute(
            select(OfferDiscount).where(
                and_(
                    OfferDiscount.discount_type == 'offer',
                    OfferDiscount.offer_id == offer_id,
                    OfferDiscount.publisher_id == publisher_id,
                    OfferDiscount.is_active == True
                )
            )
        )
        offer_discount = offer_discount_result.scalars().first()
        
        if offer_discount:
            return {
                "discount_type": "offer",
                "discount_ratio": offer_discount.discount_ratio,
                "description": f"Offer级别扣量: {offer_discount.discount_ratio}%"
            }
        
        # 查找 channel 级别
        channel_discount_result = await db.execute(
            select(OfferDiscount).where(
                and_(
                    OfferDiscount.discount_type == 'channel',
                    OfferDiscount.publisher_id == publisher_id,
                    OfferDiscount.is_active == True
                )
            )
        )
        channel_discount = channel_discount_result.scalars().first()
        
        if channel_discount:
            return {
                "discount_type": "channel",
                "discount_ratio": channel_discount.discount_ratio,
                "description": f"Channel级别扣量: {channel_discount.discount_ratio}%"
            }
        
        # 检查渠道默认扣量
        publisher_result = await db.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        publisher = publisher_result.scalars().first()
        
        if publisher and publisher.price_discount and publisher.price_discount > 0:
            return {
                "discount_type": "channel_default",
                "discount_ratio": publisher.price_discount,
                "description": f"渠道默认扣量: {publisher.price_discount}%"
            }
        
        return None
        
    except Exception as e:
        logger.error(f"获取扣量信息失败: {str(e)}", exc_info=True)
        return None

