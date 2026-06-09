"""Postback 模块 FastAPI 依赖注入定义。

封装数据库会话与管理员鉴权依赖，供 Postback 相关路由统一引用。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.models.models import User


# 数据库依赖
def get_db_dependency() -> AsyncSession:
    """
    获取异步数据库会话依赖。

    供 Postback 路由通过 Depends 注入，与全局 get_db 行为一致，
    每个请求独立会话，请求结束后自动关闭。
    """
    return get_db


# 管理员认证依赖
def get_admin_dependency() -> User:
    """
    获取管理员身份鉴权依赖。

    非管理员或令牌无效时由 require_admin 抛出 403，
    用于 Postback 管理类接口（日志查询、手动重发等）。
    """
    return require_admin
