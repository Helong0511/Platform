"""CPL 转化子模块路由聚合

职责：导出点击记录、转化扣减、转化汇总统计三类路由。

主要前缀：/clicks、/conversion-deductions、/conversion-summary。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。"""
from .clicks import router as clicks_router
from .deductions import router as deductions_router
from .summary import router as summary_router

__all__ = [
    'summary_router',
    'deductions_router',
    'clicks_router',
]
