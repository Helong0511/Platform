"""Postback 模块初始化"""
from fastapi import APIRouter
from .routes import router as postback_router
from .bft import router as bft_router
from .ip_whitelist import router as ip_whitelist_router

# 创建主路由
router = APIRouter()

# 先注册固定路由（避免被动态路由覆盖）
router.include_router(ip_whitelist_router, prefix="", tags=["postback"])

# 再注册包含动态路由的路由器
router.include_router(postback_router, prefix="", tags=["postback"])

# 导出其他路由
bft_postback = bft_router
ip_whitelist = ip_whitelist_router
