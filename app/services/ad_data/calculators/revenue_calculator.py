"""
广告收入计算器。

功能说明：
- 根据展示、点击、单价等字段计算预估/结算收入
- 统一收入公式，避免 API、导出、报表三处重复实现

在系统中的位置：
- 被 ``AdDataService`` 列表统计与报表聚合调用

注意事项：
1. 金额精度与前端展示格式（货币单位）保持一致
2. 折扣、扣减规则若有变更须同步更新本模块与 CPL 扣减配置
3. 金额计算统一使用 Decimal，避免 float 精度误差
"""
import logging
from decimal import Decimal, ROUND_DOWN

from app.core.constants import ECPM_MULTIPLIER

logger = logging.getLogger(__name__)

_ECPM_MULTIPLIER = Decimal(str(ECPM_MULTIPLIER))


class RevenueCalculator:
    """收益计算器"""

    @staticmethod
    def calculate_ecpm(
            revenue: Decimal | float | int | str | None,
            impressions: int
    ) -> Decimal:
        """
        计算 eCPM（每千次展示收益）

        Args:
            revenue: 收益
            impressions: 展示数

        Returns:
            Decimal: eCPM
        """
        if impressions <= 0:
            return Decimal("0")

        rev = Decimal(str(revenue or 0))
        ecpm = (rev / Decimal(impressions)) * _ECPM_MULTIPLIER
        return ecpm.quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    @staticmethod
    def calculate_revenue(
            ecpm: Decimal | float | int | str | None,
            impressions: int
    ) -> Decimal:
        """
        计算收益

        Args:
            ecpm: eCPM
            impressions: 展示数

        Returns:
            Decimal: 收益
        """
        if impressions <= 0:
            return Decimal("0")

        e = Decimal(str(ecpm or 0))
        revenue = (e / _ECPM_MULTIPLIER) * Decimal(impressions)
        return revenue.quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    @staticmethod
    def calculate_deducted_amount(
            original_amount: Decimal | float | int | str | None,
            deduct_ratio: Decimal | float | int | str | None
    ) -> Decimal:
        """
        计算减扣后的金额

        Args:
            original_amount: 原始金额
            deduct_ratio: 减扣比例（0-1 之间的小数，如 0.1 表示 10%）

        Returns:
            Decimal: 减扣后的金额
        """
        ratio = Decimal(str(deduct_ratio or 0))
        if ratio < 0 or ratio > 1:
            logger.warning(f"减扣比例超出范围：{ratio}，使用 0")
            ratio = Decimal("0")

        orig = Decimal(str(original_amount or 0))
        deducted = orig * (1 - ratio)
        return deducted.quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    @staticmethod
    def calculate_deduct_ratio(
            original_amount: Decimal | float | int | str | None,
            deducted_amount: Decimal | float | int | str | None
    ) -> Decimal:
        """
        计算减扣比例

        Args:
            original_amount: 原始金额
            deducted_amount: 减扣后的金额

        Returns:
            Decimal: 减扣比例
        """
        orig = Decimal(str(original_amount or 0))
        if orig <= 0:
            return Decimal("0")

        deducted = Decimal(str(deducted_amount or 0))
        ratio = (orig - deducted) / orig
        return ratio.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
