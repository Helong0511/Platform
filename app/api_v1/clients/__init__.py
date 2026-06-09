"""下游客户管理模块路由导出

职责：导出 clients 路由，挂载到 /clients 前缀。

权限：CRUD 需管理员；客户用户仅可查看/修改自身信息。

说明：统一 ResponseBaseSchema 响应包装；鉴权由各端点 Depends 声明。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。

说明：包入口，聚合子模块 router 供 api_router 注册。"""
from .clients import router

__all__ = ['router']
