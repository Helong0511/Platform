"""敏感路径探测拦截日志管理 API 路由模块。

记录并管理对外暴露敏感路径（如 .env、admin 后台）的扫描探测行为，
支持按 IP 封禁、风险等级分类、日志清理与统计查询。

路由前缀：/api/v1/system/sensitive-path-probes
权限：所有端点需管理员。

说明：系统运维接口，含定时任务、审计日志、会话、缓存、斗篷与敏感路径探测。"""
from datetime import datetime, timedelta
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.exc import StaleDataError

from app.core.audit_log import log_create, log_update, log_delete, log_deactivate, commit_audit_log
from app.core.config import settings
from app.core.sensitive_path_rules import (
    LEVEL_LABELS,
    SensitivePathLevel,
    get_level_policy,
)
from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import require_admin
from app.core.sensitive_path_guard import bust_sensitive_blocked_ip_cache
from app.core.utils import get_app_now_naive
from app.models.models import SensitivePathProbeLog, SensitiveBlockedIP, User
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)

TOP_LIMIT_MAX = 50
_BLOCKED_IP_UPSERT_RETRIES = 3
_BATCH_BLOCK_MAX_IPS = 200
_BATCH_BLOCK_MAX_LOG_IDS = 500
_IP_PATTERN = re.compile(
    r"^(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]+)$"
)


def _normalize_block_ip(raw: str) -> Optional[str]:
    """_normalize_block_ip 处理函数。（详见字段 Field description）。"""
    ip = (raw or "").strip()
    if not ip or ip.lower() == "unknown" or len(ip) > 64:
        return None
    if not _IP_PATTERN.match(ip):
        return None
    return ip


async def _upsert_sensitive_blocked_ip(
    db: AsyncSession,
    ip: str,
    reason: Optional[str],
    update_reason: bool,
) -> tuple[SensitiveBlockedIP, bool]:
    """写入或激活 IP 黑名单；并发冲突时自动重试。返回 (记录, 是否为更新)。"""
    last_exc: Optional[Exception] = None
    for _ in range(_BLOCKED_IP_UPSERT_RETRIES):
        try:
            result = await db.execute(
                select(SensitiveBlockedIP).where(SensitiveBlockedIP.blocked_ip == ip)
            )
            row = result.scalars().first()
            if row:
                row.is_active = True
                if update_reason:
                    row.reason = reason
                row.updated_at = get_app_now_naive()
                await db.commit()
                await db.refresh(row)
                return row, True

            entity = SensitiveBlockedIP(
                blocked_ip=ip,
                reason=reason,
                is_active=True,
            )
            db.add(entity)
            await db.commit()
            await db.refresh(entity)
            return entity, False
        except (IntegrityError, StaleDataError) as exc:
            last_exc = exc
            await db.rollback()
            continue

    raise last_exc or RuntimeError("封禁IP重试次数耗尽")


class BlockIPPayload(BaseModel):
    """单条 IP 封禁请求体：指定待封禁 IP 及可选原因说明。（详见字段 Field description）。"""

    blocked_ip: str = Field(..., min_length=1, max_length=64, description="待封禁IP")
    reason: Optional[str] = Field(None, max_length=255, description="封禁原因")


class CleanupPayload(BaseModel):
    """探测日志清理请求体：按保留天数删除过期记录。（详见字段 Field description）。"""

    retention_days: Optional[int] = Field(None, ge=1, le=3650, description="保留天数")


class BatchBlockIPsPayload(BaseModel):
    """批量封禁 IP（写入敏感路径黑名单）。（详见字段 Field description）。"""

    blocked_ips: Optional[list[str]] = Field(
        None, max_length=_BATCH_BLOCK_MAX_IPS, description="IP 列表"
    )
    log_ids: Optional[list[int]] = Field(
        None, max_length=_BATCH_BLOCK_MAX_LOG_IDS, description="拦截日志 ID 列表（取其 client_ip）"
    )
    reason: Optional[str] = Field(None, max_length=255, description="统一封禁原因")
    update_reason: bool = Field(False, description="已存在记录时是否更新原因")

    @model_validator(mode="after")
    def require_sources(self):
        """校验批量封禁请求至少提供 IP 列表或日志 ID 列表之一。（详见字段 Field description）。"""
        has_ips = bool(self.blocked_ips)
        has_logs = bool(self.log_ids)
        if not has_ips and not has_logs:
            raise ValueError("blocked_ips 与 log_ids 至少填写一项")
        return self


@router.get(
    "/levels",
    response_model=ResponseBaseSchema[list],
    summary="获取敏感路径预警等级与处置说明",
)
async def get_severity_levels(
    current_user: User = Depends(require_admin),
):
    """
    获取敏感路径探测的预警等级枚举及处置说明。

    权限：仅管理员；供前端筛选与展示使用。
    """
    del current_user
    levels = []
    for lv in SensitivePathLevel:
        policy = get_level_policy(lv)
        levels.append({
            "level": int(lv),
            "label": LEVEL_LABELS[int(lv)],
            "log_level": "ERROR" if policy.log_level >= 40 else ("WARNING" if policy.log_level >= 30 else "INFO"),
            "http_status": policy.http_status,
            "auto_block_threshold": policy.auto_block_threshold,
            "telegram_alert": policy.telegram_alert,
            "description": _level_description(lv),
        })
    return ResponseBaseSchema.success(data=levels, message="获取预警等级说明成功")


def _level_description(level: SensitivePathLevel) -> str:
    """_level_description 处理函数。（详见字段 Field description）。"""
    desc = {
        SensitivePathLevel.LOW: "框架指纹/文档探测，仅记录并返回404",
        SensitivePathLevel.MEDIUM: "CMS/中间件常见扫描，窗口内累计达阈值自动封禁IP",
        SensitivePathLevel.HIGH: "凭证、配置泄露与路径穿越，更低阈值自动封禁",
        SensitivePathLevel.CRITICAL: "RCE/已知利用链，最低阈值自动封禁并 Telegram 预警（防抖）",
    }
    return desc.get(level, "")


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
    severity_level: Optional[int] = Query(
        None, ge=1, le=4, description="预警等级：1低危 2中危 3高危 4危急"
    ),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    分页查询敏感路径探测拦截日志。

    权限：仅管理员；支持 IP、路径、等级、日期范围筛选。
    """
    # ---------- 入口：参数与依赖准备 ----------
    del current_user  # 仅用于权限校验
    # ---------- 异常处理 ----------
    try:
        query = select(SensitivePathProbeLog)
        count_query = select(func.count(SensitivePathProbeLog.id))

        filters = []
        # ---------- 条件分支 ----------
        if client_ip:
            filters.append(SensitivePathProbeLog.client_ip == client_ip.strip())
        # ---------- 条件分支 ----------
        if request_path:
            filters.append(SensitivePathProbeLog.request_path.like(f"%{request_path.strip()}%"))
        # ---------- 条件分支 ----------
        if matched_rule:
            filters.append(SensitivePathProbeLog.matched_rule == matched_rule.strip())
        # ---------- 条件分支 ----------
        if severity_level is not None:
            filters.append(SensitivePathProbeLog.severity_level == severity_level)
        # ---------- 条件分支 ----------
        if start_date:
            filters.append(SensitivePathProbeLog.created_at >= start_date)
        # ---------- 条件分支 ----------
        if end_date:
            filters.append(SensitivePathProbeLog.created_at <= end_date)

        # ---------- 条件分支 ----------
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

        page_ips = list({
            row.client_ip
            for row in rows
            if row.client_ip and row.client_ip != "unknown"
        })
        ip_hit_counts: dict[str, int] = {}
        blocked_ip_set: set[str] = set()
        # ---------- 条件分支 ----------
        if page_ips:
            hit_count_result = await db.execute(
                select(
                    SensitivePathProbeLog.client_ip,
                    func.count(SensitivePathProbeLog.id),
                )
                .where(SensitivePathProbeLog.client_ip.in_(page_ips))
                .group_by(SensitivePathProbeLog.client_ip)
            )
            ip_hit_counts = {ip: int(cnt) for ip, cnt in hit_count_result.all()}

            blocked_result = await db.execute(
                select(SensitiveBlockedIP.blocked_ip).where(
                    SensitiveBlockedIP.blocked_ip.in_(page_ips),
                    SensitiveBlockedIP.is_active.is_(True),
                )
            )
            blocked_ip_set = {ip for (ip,) in blocked_result.all()}

        data = [
            {
                "id": row.id,
                "request_path": row.request_path,
                "method": row.method,
                "client_ip": row.client_ip,
                "user_agent": row.user_agent,
                "query_string": row.query_string,
                "matched_rule": row.matched_rule,
                "severity_level": row.severity_level,
                "severity_label": LEVEL_LABELS.get(int(row.severity_level or 2), "中危"),
                "action_taken": row.action_taken,
                "created_at": row.created_at,
                "ip_hit_count": ip_hit_counts.get(row.client_ip, 1) if row.client_ip else 0,
                "is_blocked": bool(row.client_ip and row.client_ip in blocked_ip_set),
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
    except HTTPException:
        raise
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
    """
    分页查询敏感路径探测触发的 IP 黑名单记录。

    支持按 is_active、blocked_ip 筛选；用于安全运维审计。
    权限：仅管理员。
    """
    # ---------- 入口：参数与依赖准备 ----------
    del current_user
    # ---------- 异常处理 ----------
    try:
        query = select(SensitiveBlockedIP)
        count_query = select(func.count(SensitiveBlockedIP.id))
        filters = []
        # ---------- 条件分支 ----------
        if is_active is not None:
            filters.append(SensitiveBlockedIP.is_active == is_active)
        # ---------- 条件分支 ----------
        if blocked_ip:
            filters.append(SensitiveBlockedIP.blocked_ip.like(f"%{blocked_ip.strip()}%"))
        # ---------- 条件分支 ----------
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
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("获取黑名单IP列表失败: %s", exc, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"获取黑名单IP列表失败：{str(exc)}")


@router.post(
    "/blocked-ips",
    response_model=ResponseBaseSchema[dict],
    summary="封禁IP（写入黑名单）",
)
async def add_blocked_ip(
    request: Request,
    payload: BlockIPPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    将单个 IP 写入敏感路径黑名单。

    权限：仅管理员；封禁后该 IP 访问敏感路径将被拦截。
    """
    # ---------- 入口：参数与依赖准备 ----------
    ip = payload.blocked_ip.strip()
    # ---------- 条件分支 ----------
    if not ip:
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail="IP不能为空")
    reason = (payload.reason or "").strip() or None
    # ---------- 异常处理 ----------
    try:
        row, is_update = await _upsert_sensitive_blocked_ip(
            db=db,
            ip=ip,
            reason=reason,
            update_reason=payload.reason is not None,
        )
        # ---------- 条件分支 ----------
        if is_update:
            await log_update(
                db=db,
                user=current_user,
                resource_type="SENSITIVE_BLOCKED_IP",
                resource_id=row.id,
                resource_name=row.blocked_ip,
                request=request,
                details={"is_active": True, "reason": row.reason},
            )
            message = "IP已更新为封禁状态"
        else:
            await log_create(
                db=db,
                user=current_user,
                resource_type="SENSITIVE_BLOCKED_IP",
                resource_id=row.id,
                resource_name=row.blocked_ip,
                request=request,
                details={"reason": row.reason},
            )
            message = "IP封禁成功"
        await commit_audit_log(db)
        bust_sensitive_blocked_ip_cache()
        return ResponseBaseSchema.success(
            data={"id": row.id, "blocked_ip": row.blocked_ip, "is_active": row.is_active},
            message=message,
        )
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("封禁IP失败: %s", exc, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"封禁IP失败：{str(exc)}")


@router.post(
    "/blocked-ips/batch",
    response_model=ResponseBaseSchema[dict],
    summary="批量封禁IP（写入黑名单）",
)
async def batch_add_blocked_ips(
    request: Request,
    payload: BatchBlockIPsPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    批量将 IP 写入敏感路径黑名单。

    权限：仅管理员；支持从探测日志批量选取 IP。
    """
    # ---------- 入口：参数与依赖准备 ----------
    reason = (payload.reason or "").strip() or "批量封禁：敏感路径探测"
    ips: list[str] = []
    skipped: list[str] = []

    # ---------- 条件分支 ----------
    if payload.blocked_ips:
        # ---------- 循环处理 ----------
        for raw in payload.blocked_ips:
            ip = _normalize_block_ip(raw)
            # ---------- 条件分支 ----------
            if ip:
                ips.append(ip)
            else:
                skipped.append((raw or "").strip() or "(空)")

    # ---------- 条件分支 ----------
    if payload.log_ids:
        result = await db.execute(
            select(
                SensitivePathProbeLog.id,
                SensitivePathProbeLog.client_ip,
                SensitivePathProbeLog.request_path,
            ).where(SensitivePathProbeLog.id.in_(payload.log_ids))
        )
        rows = result.all()
        found_ids = {int(r[0]) for r in rows}
        # ---------- 循环处理 ----------
        for log_id in payload.log_ids:
            # ---------- 条件分支 ----------
            if int(log_id) not in found_ids:
                skipped.append(f"log_id:{log_id}")
        # ---------- 循环处理 ----------
        for _id, client_ip, request_path in rows:
            ip = _normalize_block_ip(client_ip or "")
            # ---------- 条件分支 ----------
            if ip:
                ips.append(ip)
            else:
                skipped.append(f"log:{_id}")

    # 去重且限制数量
    unique_ips: list[str] = []
    seen: set[str] = set()
    # ---------- 循环处理 ----------
    for ip in ips:
        # ---------- 条件分支 ----------
        if ip in seen:
            continue
        seen.add(ip)
        unique_ips.append(ip)
    # ---------- 条件分支 ----------
    if len(unique_ips) > _BATCH_BLOCK_MAX_IPS:
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=f"去重后 IP 数量超过上限 {_BATCH_BLOCK_MAX_IPS}，请分批操作",
        )
    # ---------- 条件分支 ----------
    if not unique_ips:
        raise_api_exception(ErrorCode.VALIDATION_ERROR, detail="没有可封禁的有效 IP")

    created_count = 0
    updated_count = 0
    failed: list[dict] = []

    # ---------- 循环处理 ----------
    for ip in unique_ips:
        ip_reason = reason
        # ---------- 条件分支 ----------
        if payload.log_ids and not payload.reason:
            ip_reason = f"批量封禁：敏感路径拦截日志关联 IP"
        # ---------- 异常处理 ----------
        try:
            _row, is_update = await _upsert_sensitive_blocked_ip(
                db=db,
                ip=ip,
                reason=ip_reason,
                update_reason=payload.update_reason or bool(payload.reason),
            )
            # ---------- 条件分支 ----------
            if is_update:
                updated_count += 1
            else:
                created_count += 1
        except Exception as exc:
            failed.append({"ip": ip, "error": str(exc)[:200]})

    bust_sensitive_blocked_ip_cache()

    await log_create(
        db=db,
        user=current_user,
        resource_type="SENSITIVE_BLOCKED_IP",
        resource_id=0,
        resource_name=f"批量封禁IP({created_count + updated_count}个)",
        request=request,
        details={
            "ips": unique_ips,
            "created_count": created_count,
            "updated_count": updated_count,
            "failed_count": len(failed),
            "skipped": skipped[:50],
        },
    )
    await commit_audit_log(db)

    message = (
        f"批量封禁完成：新增 {created_count}，更新 {updated_count}，"
        f"失败 {len(failed)}，跳过无效 {len(skipped)}"
    )
    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(
        data={
            "created_count": created_count,
            "updated_count": updated_count,
            "failed_count": len(failed),
            "skipped_count": len(skipped),
            "total_requested": len(unique_ips),
            "failed": failed[:20],
            "skipped": skipped[:20],
        },
        message=message,
    )


@router.post(
    "/blocked-ips/{blocked_ip_id}/unblock",
    response_model=ResponseBaseSchema[dict],
    summary="解封IP",
)
async def unblock_ip(
    request: Request,
    blocked_ip_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    将指定 ID 的 IP 从敏感路径黑名单中解除封禁。

    解除后该 IP 可再次访问平台；操作记入审计日志。
    权限：仅管理员。
    """
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
        await log_deactivate(
            db=db,
            user=current_user,
            resource_type="SENSITIVE_BLOCKED_IP",
            resource_id=row.id,
            resource_name=row.blocked_ip,
            request=request,
        )
        await commit_audit_log(db)
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
    """
    获取敏感路径探测 TOP 统计（高频 IP、高频路径）。

    权限：仅管理员。
    """
    # ---------- 入口：参数与依赖准备 ----------
    del current_user
    # ---------- 异常处理 ----------
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
        severity_result = await db.execute(
            select(
                SensitivePathProbeLog.severity_level,
                func.count(SensitivePathProbeLog.id).label("count"),
            )
            .where(SensitivePathProbeLog.created_at >= cutoff)
            .group_by(SensitivePathProbeLog.severity_level)
            .order_by(SensitivePathProbeLog.severity_level.desc())
        )
        by_severity = [
            {
                "level": int(row[0] or 2),
                "label": LEVEL_LABELS.get(int(row[0] or 2), "中危"),
                "count": int(row[1] or 0),
            }
            for row in severity_result.all()
        ]
        return ResponseBaseSchema.success(
            data={
                "days": days,
                "limit": limit,
                "top_ips": top_ips,
                "top_paths": top_paths,
                "by_severity": by_severity,
            },
            message="获取TOP统计成功",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("获取TOP统计失败: %s", exc, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"获取TOP统计失败：{str(exc)}")


@router.post(
    "/cleanup",
    response_model=ResponseBaseSchema[dict],
    summary="清理过期拦截日志",
)
async def cleanup_logs(
    request: Request,
    payload: CleanupPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    按保留天数清理过期的敏感路径拦截日志。

    权限：仅管理员。
    """
    # ---------- 入口：参数与依赖准备 ----------
    retention_days = payload.retention_days or settings.SENSITIVE_PATH_PROBE_RETENTION_DAYS
    cutoff = get_app_now_naive() - timedelta(days=retention_days)
    # ---------- 异常处理 ----------
    try:
        result = await db.execute(
            delete(SensitivePathProbeLog).where(SensitivePathProbeLog.created_at < cutoff)
        )
        deleted_count = int(result.rowcount or 0)
        await db.commit()
        await log_delete(
            db=db,
            user=current_user,
            resource_type="SENSITIVE_PATH_PROBE_LOG",
            resource_id=0,
            resource_name="敏感路径拦截日志",
            request=request,
            details={
                "deleted_count": deleted_count,
                "retention_days": retention_days,
                "cutoff": cutoff.isoformat(),
            },
        )
        await commit_audit_log(db)
        return ResponseBaseSchema.success(
            data={
                "deleted_count": deleted_count,
                "retention_days": retention_days,
                "cutoff": cutoff,
            },
            message="清理完成",
        )
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("清理敏感路径拦截日志失败: %s", exc, exc_info=True)
        raise_api_exception(ErrorCode.OPERATION_FAILED, detail=f"清理失败：{str(exc)}")
