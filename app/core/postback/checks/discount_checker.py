"""
扣量计算器

根据配置计算扣量后的金额
"""
import logging
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deduction import find_deduction_config, apply_deduction, log_deduction
from app.core.discount import calculate_discount
from app.models.models import ConversionDeductionLog

logger = logging.getLogger(__name__)


class DiscountChecker:
    """扣量计算器"""
    
    @staticmethod
    async def calculate(
        original_payout: float,
        offer_id: Optional[int],
        publisher_id: Optional[int],
        product_id: Optional[int],
        client_id: Optional[int],
        db: AsyncSession
    ) -> Tuple[float, Dict[str, Any]]:
        """
        计算扣量后的金额
        
        Args:
            original_payout: 原始金额
            offer_id: Offer ID
            publisher_id: Publisher ID
            product_id: 产品 ID
            client_id: 客户 ID
            db: 数据库会话
        
        Returns:
            tuple: (最终金额，扣量详情)
        """
        deduction_info = {
            'original_payout': original_payout,
            'offer_deduction': None,
            'publisher_deduction': None,
            'final_payout': original_payout,
        }
        
        final_payout = original_payout
        
        # 1. Offer 级别扣量
        if offer_id:
            try:
                offer_deduction = await find_deduction_config(
                    offer_id=offer_id,
                    db=db
                )
                
                if offer_deduction:
                    deducted_amount = apply_deduction(
                        original_payout,
                        offer_deduction
                    )
                    
                    deduction_info['offer_deduction'] = {
                        'config': offer_deduction,
                        'deducted': original_payout - deducted_amount,
                    }
                    
                    final_payout = deducted_amount
                    logger.debug(
                        f"Offer 扣量：offer_id={offer_id}, "
                        f"original={original_payout}, final={final_payout}"
                    )
            except Exception as e:
                logger.warning(f"Offer 扣量计算失败：{e}")
        
        # 2. Publisher 级别扣量
        if publisher_id:
            try:
                publisher_deduction = await find_deduction_config(
                    publisher_id=publisher_id,
                    db=db
                )
                
                if publisher_deduction:
                    deducted_amount = apply_deduction(
                        final_payout,
                        publisher_deduction
                    )
                    
                    deduction_info['publisher_deduction'] = {
                        'config': publisher_deduction,
                        'deducted': final_payout - deducted_amount,
                    }
                    
                    final_payout = deducted_amount
                    logger.debug(
                        f"Publisher 扣量：publisher_id={publisher_id}, "
                        f"original={original_payout}, final={final_payout}"
                    )
            except Exception as e:
                logger.warning(f"Publisher 扣量计算失败：{e}")
        
        # 3. 记录扣量日志
        if deduction_info['offer_deduction'] or deduction_info['publisher_deduction']:
            try:
                await log_deduction(
                    original_amount=original_payout,
                    final_amount=final_payout,
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                    deduction_info=deduction_info,
                    db=db
                )
            except Exception as e:
                logger.warning(f"记录扣量日志失败：{e}")
        
        deduction_info['final_payout'] = final_payout
        
        return final_payout, deduction_info
