"""
转化相关模块
提供转化统计、日志、扣减和点击记录功能
"""
from .clicks import router as clicks_router
from .deductions import router as deductions_router
from .log import router as log_router
from .summary import router as summary_router

__all__ = [
    'summary_router',
    'log_router',
    'deductions_router',
    'clicks_router',
]
