"""Redis 缓存管理 API

职责：运维侧查看、删除、批量清理缓存条目，并返回缓存健康指标。

权限：全部端点需管理员（require_admin）；受保护键（如会话）不可删除。

主要端点（前缀 /cache）：
- GET    /entries            按 SCAN 模式列出缓存键
- GET    /entries/detail     查看单个键的值与 TTL
- DELETE /entries            按 key 删除
- POST   /entries/clear-all  清除所有非受保护键
- POST   /entries/clear-pattern  按模式批量删除
- GET    /stats              缓存健康与指标。

说明：系统运维接口，含定时任务、审计日志、会话、缓存、斗篷与敏感路径探测。"""
import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.infrastructure.cache_metrics import get_cache_health_status
from app.core.security import require_admin
from app.models.models import User
from app.schemas.base import ResponseBaseSchema
from app.services.cache_management_service import (
    clear_all_cache_entries,
    delete_cache_by_pattern,
    delete_cache_entry,
    get_cache_entry,
    list_cache_entries,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class CacheDeletePatternBody(BaseModel):
    """
    按 Redis SCAN 模式批量删除缓存的请求体
    
    业务数据模型，用于 API 请求/响应的序列化与校验。
    """
    pattern: str = Field(..., min_length=1, max_length=200, description="Redis SCAN 模式")


@router.get("/entries", summary="缓存条目列表")
async def list_entries(
    pattern: str = Query("*", description="Redis SCAN 匹配模式"),
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(require_admin),
):
    """
    分页列出 Redis 缓存条目。

    权限：仅管理员；支持 pattern 模糊匹配键名。
    """
    data = await list_cache_entries(pattern=pattern, limit=limit)
    return ResponseBaseSchema.success(data=data)


@router.get("/entries/detail", summary="单个缓存详情")
async def get_entry_detail(
    key: str = Query(..., min_length=1),
    current_user: User = Depends(require_admin),
):
    """
    查看单条缓存键的值、TTL 与类型信息。

    权限：仅管理员。
    查询参数：key 为完整 Redis 键名。
    """
    entry = await get_cache_entry(key)
    if not entry:
        raise_api_exception(ErrorCode.NOT_FOUND, "缓存键不存在")
    return ResponseBaseSchema.success(data=entry)


@router.delete("/entries", summary="按 key 删除缓存")
async def delete_entry(
    key: str = Query(..., min_length=1),
    current_user: User = Depends(require_admin),
):
    """
    按 key 删除单条缓存。

    权限：仅管理员。
    受保护键（如会话）删除时返回 403。
    """
    try:
        ok = await delete_cache_entry(key)
    except ValueError as exc:
        raise_api_exception(ErrorCode.FORBIDDEN, str(exc))
    if not ok:
        raise_api_exception(ErrorCode.NOT_FOUND, "缓存键不存在或 Redis 不可用")
    return ResponseBaseSchema.success(message="缓存已清除")


@router.post("/entries/clear-all", summary="清除所有非受保护缓存")
async def clear_all_entries(current_user: User = Depends(require_admin)):
    """
    清除所有非受保护缓存键。

    权限：仅管理员；跳过系统关键键（受保护列表）。
    """
    count = await clear_all_cache_entries()
    return ResponseBaseSchema.success(
        data={"deleted": count},
        message=f"已清除 {count} 个缓存键",
    )


@router.post("/entries/clear-pattern", summary="按模式批量删除缓存")
async def clear_by_pattern(
    body: CacheDeletePatternBody,
    current_user: User = Depends(require_admin),
):
    """
    按 Redis SCAN 模式批量删除缓存键。

    权限：仅管理员。
    请求体：pattern 为 SCAN 匹配模式（如 offer:*）。
    """
    try:
        count = await delete_cache_by_pattern(body.pattern)
    except ValueError as exc:
        raise_api_exception(ErrorCode.BAD_REQUEST, str(exc))
    return ResponseBaseSchema.success(
        data={"deleted": count},
        message=f"已清除 {count} 个缓存键",
    )


@router.get("/stats", summary="缓存健康与指标")
async def cache_stats(current_user: User = Depends(require_admin)):
    """
    获取 Redis 缓存健康指标：命中率、键数量、内存占用及连接可用性。

    权限：仅管理员；用于运维面板与故障排查。
    """
    health = await get_cache_health_status()
    listing = await list_cache_entries(limit=1)
    health["redis_available"] = listing.get("redis_available", False)
    return ResponseBaseSchema.success(data=health)
