"""第三方上报日志 API

职责：查询 Meta/TikTok 等第三方 Conversions API 上报记录，用于斗篷与像素排错。

权限：仅管理员（require_admin）。

主要端点（前缀 /third-party-reports）：
- GET /              分页列表
- GET /{id}          单条详情
- GET /stats         上报统计。

说明：系统运维接口，含定时任务、审计日志、会话、缓存、斗篷与敏感路径探测。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from datetime import datetime
from time import perf_counter
from typing import Optional
import logging

from app.core.audit_log import log_update, log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.security import require_admin, get_current_user
from app.core.constants import MAX_PAGE_SIZE
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import ThirdPartyReportLog, User
from app.schemas.third_party_report import (
    ThirdPartyReportLogResponse,
    ThirdPartyReportLogListResponse,
    ThirdPartyReportLogResponseList,
    ThirdPartyReportLogResponseSingle,
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from pydantic import BaseModel, Field
from app.core.third_party_report import retry_report_log, update_report_log_params

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


class UpdateReportLogParams(BaseModel):
    """
    更新第三方上报日志参数模型
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    adsid: Optional[str] = Field(None, max_length=500, description="广告ID")
    event: Optional[str] = Field(None, max_length=50, description="事件类型")
    conversion_id: Optional[str] = Field(None, max_length=255, description="转化ID")
    currency: Optional[str] = Field(None, max_length=10, description="货币类型")
    amount: Optional[float] = Field(None, description="支付金额")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    ip: Optional[str] = Field(None, max_length=50, description="IP地址")
    phone: Optional[str] = Field(None, max_length=50, description="手机号")
    ua: Optional[str] = Field(None, description="用户代理")
    report_params: Optional[str] = Field(None, description="完整上报参数（JSON格式）")
    use_hash: Optional[bool] = Field(None, description="是否对email、ip、phone进行哈希处理")


@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list[ThirdPartyReportLogListResponse]],
    summary="获取第三方上报日志列表",
    description="查询第三方上报日志，支持多种筛选条件，仅管理员可访问"
)
async def get_third_party_reports(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
        source: Optional[str] = Query(None, max_length=50, description="来源筛选"),
        adsid: Optional[str] = Query(None, max_length=500, description="广告ID筛选"),
        event: Optional[str] = Query(None, max_length=50, description="事件类型筛选"),
        status: Optional[str] = Query(None, max_length=20, description="状态筛选"),
        start_date: Optional[datetime] = Query(None, description="开始时间"),
        end_date: Optional[datetime] = Query(None, description="结束时间"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取第三方上报日志列表
    
    支持以下筛选条件：
    - 来源（short_link, postback）
    - 广告ID
    - 事件类型
    - 状态（pending, success, failed）
    - 时间范围
    """
    # ---------- 入口：参数与依赖准备 ----------
    started_at = perf_counter()
    # ---------- 异常处理 ----------
    try:
        # 构建查询
        query = select(ThirdPartyReportLog)
        count_query = select(func.count(ThirdPartyReportLog.id))

        # 添加筛选条件
        filters = []
        # ---------- 条件分支 ----------
        if source:
            filters.append(ThirdPartyReportLog.source == source)
        # ---------- 条件分支 ----------
        if adsid:
            filters.append(ThirdPartyReportLog.adsid == adsid)
        # ---------- 条件分支 ----------
        if event:
            filters.append(ThirdPartyReportLog.event == event)
        # ---------- 条件分支 ----------
        if status:
            filters.append(ThirdPartyReportLog.status == status)
        # ---------- 条件分支 ----------
        if start_date:
            filters.append(ThirdPartyReportLog.created_at >= start_date)
        # ---------- 条件分支 ----------
        if end_date:
            filters.append(ThirdPartyReportLog.created_at <= end_date)

        # ---------- 条件分支 ----------
        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # 排序（按创建时间倒序）
        query = query.order_by(ThirdPartyReportLog.created_at.desc())

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # 执行查询
        list_started_at = perf_counter()
        result = await db.execute(query)
        logs = result.scalars().all()
        list_elapsed_ms = int((perf_counter() - list_started_at) * 1000)

        # 获取总数
        count_started_at = perf_counter()
        count_result = await db.execute(count_query)
        total = count_result.scalar_one()
        count_elapsed_ms = int((perf_counter() - count_started_at) * 1000)

        # 转换为响应模型
        serialize_started_at = perf_counter()
        log_responses = []
        # ---------- 循环处理 ----------
        for log in logs:
            item = ThirdPartyReportLogListResponse.model_validate(log).model_dump()
            # ---------- 条件分支 ----------
            if log.report_params:
                preview = log.report_params[:120]
                item["report_params_preview"] = f"{preview}..." if len(log.report_params) > 120 else preview
            else:
                item["report_params_preview"] = None
            log_responses.append(item)
        serialize_elapsed_ms = int((perf_counter() - serialize_started_at) * 1000)
        total_elapsed_ms = int((perf_counter() - started_at) * 1000)

        logger.info(
            "第三方上报日志列表耗时: total=%sms, query=%sms, count=%sms, serialize=%sms, rows=%s, total_count=%s, page=%s, page_size=%s",
            total_elapsed_ms,
            list_elapsed_ms,
            count_elapsed_ms,
            serialize_elapsed_ms,
            len(log_responses),
            total,
            page,
            page_size,
        )

        return PaginatedResponseBaseSchema.success(
            data=log_responses,
            total=total,
            page=page,
            page_size=page_size,
            message="获取第三方上报日志列表成功"
        )
    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"获取第三方上报日志列表失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取日志列表失败：{str(e)}"
        )


@router.get(
    "/stats/summary",
    response_model=ResponseBaseSchema[dict],
    summary="获取第三方上报统计摘要",
    description="获取第三方上报的统计信息，仅管理员可访问"
)
async def get_third_party_report_stats(
        start_date: Optional[datetime] = Query(None, description="开始时间"),
        end_date: Optional[datetime] = Query(None, description="结束时间"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取第三方上报统计摘要
    
    返回：
    - 总上报数
    - 成功/失败数量
    - 各来源数量
    - 各事件类型数量
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        # 基础筛选条件
        filters = []
        # ---------- 条件分支 ----------
        if start_date:
            filters.append(ThirdPartyReportLog.created_at >= start_date)
        # ---------- 条件分支 ----------
        if end_date:
            filters.append(ThirdPartyReportLog.created_at <= end_date)

        where_clause = and_(*filters) if filters else True

        # 总上报数
        total_query = select(func.count(ThirdPartyReportLog.id)).where(where_clause)
        total_result = await db.execute(total_query)
        total = total_result.scalar_one()

        # 成功数量
        success_query = select(func.count(ThirdPartyReportLog.id)).where(
            and_(where_clause, ThirdPartyReportLog.status == "success")
        )
        success_result = await db.execute(success_query)
        success_count = success_result.scalar_one()

        # 失败数量
        failed_query = select(func.count(ThirdPartyReportLog.id)).where(
            and_(where_clause, ThirdPartyReportLog.status == "failed")
        )
        failed_result = await db.execute(failed_query)
        failed_count = failed_result.scalar_one()

        # 按来源统计
        source_stats_query = select(
            ThirdPartyReportLog.source,
            func.count(ThirdPartyReportLog.id)
        ).where(where_clause).group_by(ThirdPartyReportLog.source)
        source_stats_result = await db.execute(source_stats_query)
        source_stats = {row[0]: row[1] for row in source_stats_result.all()}

        # 按事件类型统计
        event_stats_query = select(
            ThirdPartyReportLog.event,
            func.count(ThirdPartyReportLog.id)
        ).where(where_clause).group_by(ThirdPartyReportLog.event)
        event_stats_result = await db.execute(event_stats_query)
        event_stats = {row[0]: row[1] for row in event_stats_result.all()}

        stats = {
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "pending": total - success_count - failed_count,
            "source_stats": source_stats,
            "event_stats": event_stats
        }

        return ResponseBaseSchema.success(
            data=stats,
            message="获取统计信息成功"
        )
    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"获取第三方上报统计信息失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取统计信息失败：{str(e)}"
        )


@router.get(
    "/{log_id}",
    response_model=ResponseBaseSchema[ThirdPartyReportLogResponse],
    summary="获取第三方上报日志详情",
    description="根据日志ID获取详细信息，仅管理员可访问"
)
async def get_third_party_report(
        log_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    按 ID 获取单条第三方上报日志详情。

    权限：仅管理员。
    含上报参数、响应状态、重试次数等调试信息。
    """
    try:
        # 查询日志
        result = await db.execute(
            select(ThirdPartyReportLog).where(ThirdPartyReportLog.id == log_id)
        )
        log = result.scalar_one_or_none()

        if not log:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="日志记录不存在"
            )

        return ResponseBaseSchema.success(
            data=ThirdPartyReportLogResponse.model_validate(log),
            message="获取日志详情成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取第三方上报日志详情失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取日志详情失败：{str(e)}"
        )


@router.put(
    "/{log_id}",
    response_model=ResponseBaseSchema[dict],
    summary="更新第三方上报日志参数",
    description="更新第三方上报日志的参数，仅管理员可访问"
)
async def update_third_party_report(
        request: Request,
        log_id: int,
        params: UpdateReportLogParams,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    更新第三方上报日志的上报参数。

    权限：仅管理员。
    可修改 adsid、event、conversion_id 等字段；变更写审计日志。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        success = await update_report_log_params(
            log_id=log_id,
            adsid=params.adsid,
            event=params.event,
            conversion_id=params.conversion_id,
            currency=params.currency,
            amount=params.amount,
            email=params.email,
            ip=params.ip,
            phone=params.phone,
            ua=params.ua,
            report_params=params.report_params,
            use_hash=params.use_hash
        )
        
        # ---------- 条件分支 ----------
        if not success:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="日志记录不存在或更新失败"
            )

        await log_update(
            db=db,
            user=current_user,
            resource_type="THIRD_PARTY_REPORT_LOG",
            resource_id=log_id,
            resource_name=f"第三方上报日志-{log_id}",
            request=request,
            details={"updated_fields": list(params.model_dump(exclude_unset=True).keys())},
        )
        await commit_audit_log(db)

        return ResponseBaseSchema.success(
            data={"success": True},
            message="更新日志参数成功"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新第三方上报日志参数失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新日志参数失败：{str(e)}"
        )


@router.post(
    "/{log_id}/retry",
    response_model=ResponseBaseSchema[dict],
    summary="重新上报第三方上报日志",
    description="触发重新上报指定的第三方上报日志，仅管理员可访问"
)
async def retry_third_party_report(
        request: Request,
        log_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    对失败的第三方上报记录执行手动重试。

    权限：仅管理员。
    触发重新上报并更新日志状态；操作写审计日志。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        success = await retry_report_log(log_id)
        
        # ---------- 条件分支 ----------
        if not success:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="日志记录不存在或重新上报失败"
            )

        await log_user_action(
            db=db,
            action_type="TASK_RUN",
            user=current_user,
            resource_type="THIRD_PARTY_REPORT_LOG",
            resource_id=log_id,
            resource_name=f"第三方上报重试-{log_id}",
            request=request,
        )
        await commit_audit_log(db)

        return ResponseBaseSchema.success(
            data={"success": True},
            message="已触发重新上报，请稍后刷新查看结果"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新上报第三方上报日志失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"重新上报失败：{str(e)}"
        )
