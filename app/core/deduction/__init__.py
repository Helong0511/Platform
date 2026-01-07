"""
扣减管理模块
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

