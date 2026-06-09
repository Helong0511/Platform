"""CPL 业务模块路由聚合

职责：导出广告主、渠道、Offer、Cap、扣量、转化统计等子路由。

权限：多数写操作需管理员；列表/详情按角色过滤。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。"""
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
