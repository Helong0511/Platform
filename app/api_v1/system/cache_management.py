"""缓存管理 API（管理员）。"""
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
    pattern: str = Field(..., min_length=1, max_length=200, description="Redis SCAN 模式")


@router.get("/entries", summary="缓存条目列表")
async def list_entries(
    pattern: str = Query("*", description="Redis SCAN 匹配模式"),
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(require_admin),
):
    data = await list_cache_entries(pattern=pattern, limit=limit)
    return ResponseBaseSchema.success(data=data)


@router.get("/entries/detail", summary="单个缓存详情")
async def get_entry_detail(
    key: str = Query(..., min_length=1),
    current_user: User = Depends(require_admin),
):
    entry = await get_cache_entry(key)
    if not entry:
        raise_api_exception(ErrorCode.NOT_FOUND, "缓存键不存在")
    return ResponseBaseSchema.success(data=entry)


@router.delete("/entries", summary="按 key 删除缓存")
async def delete_entry(
    key: str = Query(..., min_length=1),
    current_user: User = Depends(require_admin),
):
    try:
        ok = await delete_cache_entry(key)
    except ValueError as exc:
        raise_api_exception(ErrorCode.FORBIDDEN, str(exc))
    if not ok:
        raise_api_exception(ErrorCode.NOT_FOUND, "缓存键不存在或 Redis 不可用")
    return ResponseBaseSchema.success(message="缓存已清除")


@router.post("/entries/clear-all", summary="清除所有非受保护缓存")
async def clear_all_entries(current_user: User = Depends(require_admin)):
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
    health = await get_cache_health_status()
    listing = await list_cache_entries(limit=1)
    health["redis_available"] = listing.get("redis_available", False)
    return ResponseBaseSchema.success(data=health)
