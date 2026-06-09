"""ML 列映射训练模块

职责：Excel 列名智能匹配与映射规则持久化。

权限：需管理员。

说明：统一 ResponseBaseSchema 响应包装；鉴权由各端点 Depends 声明。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。

说明：包入口，聚合子模块 router 供 api_router 注册。"""
from .ml_model import router

__all__ = ['router']
