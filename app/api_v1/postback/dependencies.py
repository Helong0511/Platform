"""Postback 模块依赖项"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.models.models import User


# 数据库依赖
def get_db_dependency() -> AsyncSession:
    """获取数据库会话"""
    return get_db


# 管理员认证依赖
def get_admin_dependency() -> User:
    """获取管理员用户"""
    return require_admin
