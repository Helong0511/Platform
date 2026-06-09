"""点击追踪与短链接模块

职责：Offer 点击跳转追踪、短链接 CRUD。

权限：追踪跳转公开；短链接管理需登录。

说明：点击追踪与短链接服务，记录访问并对接斗篷跳转。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。"""
from .tracking import router
from .short_links import router as short_links_router

__all__ = ['router', 'short_links_router']

