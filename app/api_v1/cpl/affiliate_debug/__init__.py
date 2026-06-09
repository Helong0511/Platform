"""CPL 下游联调测试模块

职责：导出 affiliate_tests 路由，用于模拟渠道点击与 Postback 链路验证。

权限：需管理员。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。"""
from .affiliate_tests import router as affiliate_tests_router

__all__ = [
    'affiliate_tests_router',
]
