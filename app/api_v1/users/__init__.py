"""用户管理模块路由导出

职责：用户 CRUD、密码修改、数据导出。

权限：管理端 CRUD 需管理员；/me 接口用户自助。

说明：统一 ResponseBaseSchema 响应包装；鉴权由各端点 Depends 声明。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。

说明：包入口，聚合子模块 router 供 api_router 注册。"""
from .users import router

__all__ = ['router']

