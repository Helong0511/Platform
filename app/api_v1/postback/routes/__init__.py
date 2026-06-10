"""Postback 管理端路由聚合。"""
from fastapi import APIRouter

from . import conversions, forward_logs, pending, diagnostic, receive

router = APIRouter()
router.include_router(conversions.router)
router.include_router(forward_logs.router)
router.include_router(pending.router)
router.include_router(diagnostic.router)
router.include_router(receive.router)
