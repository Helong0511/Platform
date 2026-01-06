"""
CPL测试模块
提供上游和下游测试功能
"""
from .advertiser_tests import router as advertiser_tests_router
from .affiliate_tests import router as affiliate_tests_router

__all__ = [
    'advertiser_tests_router',
    'affiliate_tests_router',
]

