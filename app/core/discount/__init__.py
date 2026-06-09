"""
扣量管理模块（app/core/discount）。

按 Offer/渠道/产品等维度计算渠道结算 payout（扣量比例），
供 Postback 流水线 step_apply_discount 调用。
"""
from app.core.discount.discount_manager import (
    calculate_discount,
    get_discount_info
)

__all__ = [
    "calculate_discount",
    "get_discount_info",
]

