"""
CPL系统模块
提供CPL相关的所有功能，包括广告主、渠道、Offer、转化等
"""
from .advertisers import router as advertisers_router
from .affiliate_debug import affiliate_tests_router
from .caps import router as caps_router
from .conversions.clicks import router as clicks_router
from .conversions.deductions import router as conversion_deductions_router
from .conversions.summary import router as conversion_summary_router
from .discounts import router as discounts_router
from .offers import router as offers_router
from .publishers import router as publishers_router

__all__ = [
    'advertisers_router',
    'publishers_router',
    'offers_router',
    'caps_router',
    'discounts_router',
    'conversion_deductions_router',
    'conversion_summary_router',
    'clicks_router',
    'affiliate_tests_router',
]
