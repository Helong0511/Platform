"""
收益计算器

计算广告收益（eCPM、Revenue 等）
"""
import logging
from typing import Optional

from app.core.constants import ECPM_MULTIPLIER

logger = logging.getLogger(__name__)


class RevenueCalculator:
    """收益计算器"""
    
    @staticmethod
    def calculate_ecpm(
        revenue: float,
        impressions: int
    ) -> float:
        """
        计算 eCPM（每千次展示收益）
        
        Args:
            revenue: 收益
            impressions: 展示数
        
        Returns:
            float: eCPM
        """
        if impressions <= 0:
            return 0.0
        
        ecpm = (revenue / impressions) * ECPM_MULTIPLIER
        return round(ecpm, 2)
    
    @staticmethod
    def calculate_revenue(
        ecpm: float,
        impressions: int
    ) -> float:
        """
        计算收益
        
        Args:
            ecpm: eCPM
            impressions: 展示数
        
        Returns:
            float: 收益
        """
        if impressions <= 0:
            return 0.0
        
        revenue = (ecpm / ECPM_MULTIPLIER) * impressions
        return round(revenue, 2)
    
    @staticmethod
    def calculate_deducted_amount(
        original_amount: float,
        deduct_ratio: float
    ) -> float:
        """
        计算减扣后的金额
        
        Args:
            original_amount: 原始金额
            deduct_ratio: 减扣比例（0-1 之间的小数，如 0.1 表示 10%）
        
        Returns:
            float: 减扣后的金额
        """
        if deduct_ratio < 0 or deduct_ratio > 1:
            logger.warning(f"减扣比例超出范围：{deduct_ratio}，使用 0")
            deduct_ratio = 0
        
        deducted = original_amount * (1 - deduct_ratio)
        return round(deducted, 2)
    
    @staticmethod
    def calculate_deduct_ratio(
        original_amount: float,
        deducted_amount: float
    ) -> float:
        """
        计算减扣比例
        
        Args:
            original_amount: 原始金额
            deducted_amount: 减扣后的金额
        
        Returns:
            float: 减扣比例
        """
        if original_amount <= 0:
            return 0.0
        
        ratio = (original_amount - deducted_amount) / original_amount
        return round(ratio, 4)
