"""产品管理模块路由导出

职责：产品 CRUD 与产品分配历史查询。

权限：管理员全量；客户仅操作自身产品。

说明：统一 ResponseBaseSchema 响应包装；鉴权由各端点 Depends 声明。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。

说明：包入口，聚合子模块 router 供 api_router 注册。"""
from .products import router
from .assignments import router as assignments_router

__all__ = ['router', 'assignments_router']

