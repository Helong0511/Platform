"""认证模块路由聚合

职责：合并 login/logout 与 refresh 子路由，统一挂载到 /auth 前缀。

主要端点：
- POST /auth/login      用户登录
- POST /auth/logout     用户登出
- POST /auth/refresh    刷新访问令牌

当前用户信息请使用 GET /users/me（users 模块），本包不提供 /auth/me。

说明：用户认证，含登录、刷新令牌、登出及 JWT 校验。"""
# 合并路由
from fastapi import APIRouter

from .auth import router as auth_router
from .refresh import router as refresh_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(refresh_router)

__all__ = ['router']
