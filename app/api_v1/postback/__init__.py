"""Postback 服务模块

职责：统一 Postback 回调接收、转化管理、BFT 兼容路由、IP 白名单。

外部回调无需登录；管理端接口需管理员。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。"""
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
