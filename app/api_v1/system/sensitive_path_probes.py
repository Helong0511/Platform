"""敏感路径探测拦截日志管理 API。"""
from datetime import datetime, timedelta
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import require_admin
from app.core.utils import get_app_now_naive
from app.models.models import SensitivePathProbeLog, SensitiveBlockedIP, User
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)

TOP_LIMIT_MAX = 50


class BlockIPPayload(BaseModel):
    blocked_ip: str = Field(..., min_length=1, max_length=64, description="待封禁IP")
    reason: Optional[str] = Field(None, max_length=255, description="封禁原因")


class CleanupPayload(BaseModel):
    retention_days: Optional[int] = Field(None, ge=1, le=3650, description="保留天数")


@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list],
    summary="获取敏感路径探测拦截日志列表",
)
async def get_sensitive_path_probe_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    client_ip: Optional[str] = Query(None, description="客户端IP"),
    request_path: Optional[str] = Query(None, description="请求路径（模糊匹配）"),
    matched_rule: Optional[str] = Query(None, description="命中规则"),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    del current_user  # 仅用于权限校验
    try:
        query = select(SensitivePathProbeLog)
        count_query = select(func.count(SensitivePathProbeLog.id))

        filters = []
        if client_ip:
            filters.append(SensitivePathProbeLog.client_ip == client_ip.strip())
        if request_path:
            filters.append(SensitivePathProbeLog.request_path.like(f"%{request_path.strip()}%"))
        if matched_rule:
            filters.append(SensitivePathProbeLog.matched_rule == matched_rule.strip())
        if start_date:
            filters.append(SensitivePathProbeLog.created_at >= start_date)
        if end_date:
            filters.append(SensitivePathProbeLog.created_at <= end_date)

        if filters:
            where_clause = and_(*filters)
            query = query.where(where_clause)
            count_query = count_query.where(where_clause)

        query = query.order_by(SensitivePathProbeLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        rows = result.scalars().all()

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        data = [
            {
                "id": row.id,
                "request_path": row.request_path,
                "method": row.method,
                "client_ip": row.client_ip,
                "user_agent": row.user_agent,
                "query_string": row.query_string,
                "matched_rule": row.matched_rule,
                "created_at": row.created_at,
            }
            for row in rows
        ]

        return PaginatedResponseBaseSchema.success(
            data=data,
            total=total,
            page=page,
            page_size=page_size,
            message="获取敏感路径探测拦截日志成功",
        )
    except Exception as exc:
        logger.error("获取敏感路径探测拦截日志失败: %s", exc, exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取敏感路径探测拦截日志失败：{str(exc)}",
        )


@router.get(
    "/blocked-ips",
    response_model=PaginatedResponseBaseSchema[list],
    summary="获取敏感路径黑名单IP列表",
)
async def get_blocked_ips(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
    blocked_ip: Optional[str] = Query(None, description="IP筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    del current_user
    try:
        query = select(SensitiveBlockedIP)
        count_query = select(func.count(SensitiveBlockedIP.id))
        filters = []
        if is_active is not None:
            filters.append(SensitiveBlockedIP.is_active == is_active)
        if blocked_ip:
            filters.append(SensitiveBlockedIP.blocked_ip.like(f"%{blocked_ip.strip()}%"))
        if filters:
            where_clause = and_(*filters)
            query = query.where(where_clause)
            count_query = count_query.where(where_clause)
        query = query.order_by(SensitiveBlockedIP.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        rows = (await db.execute(query)).scalars().all()
        total = (await db.execute(count_query)).scalar() or 0
        data = [
            {
                "id": row.id,
                "blocked_ip": row.blocked_ip,
                "reason": row.reason,
                "is_active": row.is_active,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
        return PaginatedResponseBaseSchema.success(
            data=data,
            total=total,
            page=page,
            page_size=page_size,
            message="获取黑名单IP列表成功",
        )
    except Exception as exc:
        logger.error("获取黑名单IP列表失败: %s", exc, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"获取黑名单IP列表失败：{str(exc)}")


@router.post(
    "/blocked-ips",
    response_model=ResponseBaseSchema[dict],
    summary="封禁IP（写入黑名单）",
)
async def add_blocked_ip(
    payload: BlockIPPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    del current_user
    ip = payload.blocked_ip.strip()
    if not ip:
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail="IP不能为空")
    try:
        result = await db.execute(
            select(SensitiveBlockedIP).where(SensitiveBlockedIP.blocked_ip == ip)
        )
        row = result.scalars().first()
        if row:
            row.is_active = True
            if payload.reason is not None:
                row.reason = payload.reason.strip() or None
            row.updated_at = get_app_now_naive()
            await db.commit()
            await db.refresh(row)
            data = {"id": row.id, "blocked_ip": row.blocked_ip, "is_active": row.is_active}
            return ResponseBaseSchema.success(data=data, message="IP已更新为封禁状态")

        entity = SensitiveBlockedIP(
            blocked_ip=ip,
            reason=(payload.reason or "").strip() or None,
            is_active=True,
        )
        db.add(entity)
        await db.commit()
        await db.refresh(entity)
        return ResponseBaseSchema.success(
            data={"id": entity.id, "blocked_ip": entity.blocked_ip, "is_active": entity.is_active},
            message="IP封禁成功",
        )
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("封禁IP失败: %s", exc, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"封禁IP失败：{str(exc)}")


@router.post(
    "/blocked-ips/{blocked_ip_id}/unblock",
    response_model=ResponseBaseSchema[dict],
    summary="解封IP",
)
async def unblock_ip(
    blocked_ip_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    del current_user
    try:
        result = await db.execute(
            select(SensitiveBlockedIP).where(SensitiveBlockedIP.id == blocked_ip_id)
        )
        row = result.scalars().first()
        if not row:
            raise_api_exception(ErrorCode.RESOURCE_NOT_FOUND, detail="黑名单记录不存在")
        row.is_active = False
        row.updated_at = get_app_now_naive()
        await db.commit()
        return ResponseBaseSchema.success(
            data={"id": row.id, "blocked_ip": row.blocked_ip, "is_active": row.is_active},
            message="IP已解封",
        )
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("解封IP失败: %s", exc, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"解封IP失败：{str(exc)}")


@router.get(
    "/stats/top",
    response_model=ResponseBaseSchema[dict],
    summary="获取TOP统计（IP/路径）",
)
async def get_top_stats(
    days: int = Query(7, ge=1, le=3650, description="统计最近N天"),
    limit: int = Query(10, ge=1, le=TOP_LIMIT_MAX, description="TOP数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    del current_user
    try:
        cutoff = get_app_now_naive() - timedelta(days=days)
        top_ip_result = await db.execute(
            select(
                SensitivePathProbeLog.client_ip,
                func.count(SensitivePathProbeLog.id).label("count")
            )
            .where(SensitivePathProbeLog.created_at >= cutoff)
            .group_by(SensitivePathProbeLog.client_ip)
            .order_by(func.count(SensitivePathProbeLog.id).desc())
            .limit(limit)
        )
        top_path_result = await db.execute(
            select(
                SensitivePathProbeLog.request_path,
                func.count(SensitivePathProbeLog.id).label("count")
            )
            .where(SensitivePathProbeLog.created_at >= cutoff)
            .group_by(SensitivePathProbeLog.request_path)
            .order_by(func.count(SensitivePathProbeLog.id).desc())
            .limit(limit)
        )
        top_ips = [
            {"name": (row[0] or "unknown"), "count": int(row[1] or 0)}
            for row in top_ip_result.all()
        ]
        top_paths = [
            {"name": (row[0] or "/"), "count": int(row[1] or 0)}
            for row in top_path_result.all()
        ]
        return ResponseBaseSchema.success(
            data={"days": days, "limit": limit, "top_ips": top_ips, "top_paths": top_paths},
            message="获取TOP统计成功",
        )
    except Exception as exc:
        logger.error("获取TOP统计失败: %s", exc, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"获取TOP统计失败：{str(exc)}")


@router.post(
    "/cleanup",
    response_model=ResponseBaseSchema[dict],
    summary="清理过期拦截日志",
)
async def cleanup_logs(
    payload: CleanupPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    del current_user
    retention_days = payload.retention_days or settings.SENSITIVE_PATH_PROBE_RETENTION_DAYS
    cutoff = get_app_now_naive() - timedelta(days=retention_days)
    try:
        result = await db.execute(
            delete(SensitivePathProbeLog).where(SensitivePathProbeLog.created_at < cutoff)
        )
        deleted_count = int(result.rowcount or 0)
        await db.commit()
        return ResponseBaseSchema.success(
            data={
                "deleted_count": deleted_count,
                "retention_days": retention_days,
                "cutoff": cutoff,
            },
            message="清理完成",
        )
    except Exception as exc:
        await db.rollback()
        logger.error("清理敏感路径拦截日志失败: %s", exc, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"清理失败：{str(exc)}")
