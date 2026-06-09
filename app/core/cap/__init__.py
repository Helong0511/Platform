"""
Cap 管理模块（app/core/cap）。

提供 Offer/渠道日 cap 与总 cap 的检查、计数、Redis 原子递增及一致性校验，
在 Postback 流水线中限制转化超量。
"""
from app.core.cap.cap_manager import (
    check_cap,
    increment_cap_count,
    reset_daily_caps
)
from app.core.cap.consistency_checker import check_cap_consistency

__all__ = [
    "check_cap",
    "increment_cap_count",
    "reset_daily_caps",
    "check_cap_consistency",
]

