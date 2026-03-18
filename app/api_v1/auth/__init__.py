"""
认证模块
提供用户登录、登出、令牌刷新等认证功能
"""
# 合并路由
from fastapi import APIRouter

from .auth import router as auth_router
from .refresh import router as refresh_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(refresh_router)

__all__ = ['router']
