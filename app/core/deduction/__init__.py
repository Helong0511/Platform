"""
转化扣减（Deduction）管理包。

对外导出：按 offer/publisher/advertiser 查找扣减配置、应用扣减策略与统计接口。
"""
from app.core.deduction.deduction_manager import (
    # 向后兼容的函数接口
    find_deduction_config,
    apply_deduction,
    log_deduction,
    get_recent_conversion_stats,
    # 新的类接口
    DeductionManager,
    DeductionResult,
    ConversionStats,
    # 策略类
    DeductionStrategy,
    RandomDeductionStrategy,
    ProportionalDeductionStrategy,
    RoundRobinDeductionStrategy,
    DeductionStrategyFactory,
)

__all__ = [
    # 向后兼容的函数接口
    "find_deduction_config",
    "apply_deduction",
    "log_deduction",
    "get_recent_conversion_stats",
    # 新的类接口
    "DeductionManager",
    "DeductionResult",
    "ConversionStats",
    # 策略类
    "DeductionStrategy",
    "RandomDeductionStrategy",
    "ProportionalDeductionStrategy",
    "RoundRobinDeductionStrategy",
    "DeductionStrategyFactory",
]

