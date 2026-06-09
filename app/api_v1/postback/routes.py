"""Postback 管理端路由定义

职责：将 HTTP 请求委托给 handlers 子模块，覆盖转化查询、统计、转发日志、
待确认记录、诊断与平台回调接收等能力。

权限：
- 管理端查询/操作接口均需 require_admin
- /postback/{platform} 为外部平台回调入口，无需登录

主要端点：
- GET  /postback/conversions          转化记录分页查询
- GET  /postback/stats                转化统计
- GET  /postback/forward-logs         下游转发日志
- POST /postback/forward-logs/{id}/resend  补发转发
- GET  /postback/diagnose             单条记录诊断
- PUT  /postback/conversions/{id}/status   更新转化状态
- GET/POST /postback/pending-conversions/* 待确认记录管理
- GET  /postback/check-duplicates     重复转化检查
- GET/POST /postback/{platform}       接收上游 Postback 回调。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
from fastapi import APIRouter, Request, Query, Depends, Path, Response
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_update, log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.security import require_admin
from app.models.models import User

from .handlers import (
    conversion_handler,
    stats_handler,
    forward_log_handler,
    diagnostic_handler,
    pending_handler,
    duplicate_handler,
    receive_handler
)

# 创建路由实例
router = APIRouter()

# ====== 查询接口（必须在动态路径之前定义） ======
@router.get("/postback/conversions",
            summary="查询 PostBack 转化记录（管理员，已融合转化日志功能）")
async def get_postback_conversions(
        request: Request,
        platform: Optional[str] = Query(None, description="平台名称"),
        product_id: Optional[int] = Query(None, description="产品ID"),
        client_id: Optional[int] = Query(None, description="客户ID"),
        conversion_or_click_id: Optional[str] = Query(None, description="转化ID或点击ID"),
        # 转化日志筛选条件（融合功能）
        click_id: Optional[str] = Query(None, description="Click ID过滤"),
        offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
        publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        conversion_status: Optional[str] = Query(None,
                                                 description="转化状态过滤（Pending/Approved/CapReached/OfferInactive/ClickExpired）"),
        start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=1000, description="每页数量"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    分页查询 PostBack 转化记录（已融合原转化日志功能）。

    权限：仅管理员。
    筛选：平台、产品、客户、Click ID、Offer、渠道、广告主、转化状态、日期范围等。
    实现：委托 conversion_handler，支持多维度组合过滤。
    """
    return await conversion_handler.get_postback_conversions(
        request, platform, product_id, client_id, conversion_or_click_id,
        click_id, offer_id, publisher_id, advertiser_id, conversion_status,
        start_date, end_date, page, page_size, db, current_user
    )


@router.get("/postback/stats",
            summary="PostBack 统计信息（管理员）")
async def get_postback_stats(
        request: Request,
        platform: Optional[str] = Query(None, description="平台名称"),
        start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取 PostBack 转化统计数据。

    权限：仅管理员。
    可按平台、日期范围聚合转化数量、成功率等指标。
    """
    return await stats_handler.get_postback_stats(
        platform=platform,
        start_date=start_date,
        end_date=end_date,
        db=db,
        current_user=current_user,
    )


# ====== 转发日志查询接口（必须在动态路径之前定义） ======
@router.get("/postback/forward-logs",
            summary="查询 PostBack 下游转发日志（管理员）")
async def get_postback_forward_logs(
        request: Request,
        conversion_id: Optional[int] = Query(None, description="转化记录ID"),
        product_id: Optional[int] = Query(None, description="产品ID"),
        publisher_id: Optional[int] = Query(None, description="渠道ID"),
        success: Optional[bool] = Query(None, description="是否成功"),
        start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=1000, description="每页数量"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    分页查询下游 Postback 转发日志。

    权限：仅管理员。
    筛选：转化 ID、产品、渠道、成功/失败、日期范围。
    用于排查下游客户未收到转化回传的问题。
    """
    return await forward_log_handler.get_postback_forward_logs(
        request, conversion_id, product_id, publisher_id, success,
        start_date, end_date, page, page_size, db, current_user
    )


# ====== 补发转发接口 ======
@router.post("/postback/forward-logs/{forward_log_id}/resend",
             summary="补发 PostBack 转发（管理员）")
async def resend_postback_forward(
        request: Request,
        forward_log_id: int = Path(..., ge=1, description="转发日志ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    对指定转发日志记录执行手动补发。

    权限：仅管理员。
    路径参数：forward_log_id 为转发日志主键。
    补发成功后写审计日志（action_type=TASK_RUN）。
    """
    result = await forward_log_handler.resend_postback_forward(
        forward_log_id, db, current_user
    )
    await log_user_action(
        db=db,
        action_type="TASK_RUN",
        user=current_user,
        resource_type="POSTBACK_FORWARD_LOG",
        resource_id=forward_log_id,
        resource_name=f"Postback转发补发-{forward_log_id}",
        request=request,
    )
    await commit_audit_log(db)
    return result


# ====== 诊断工具接口 ======
@router.get("/postback/diagnose",
            summary="诊断 PostBack 记录问题（管理员）")
async def diagnose_postback_record(
        conversion_or_click_id: str = Query(..., description="转化ID或点击ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    诊断单条 Postback/转化记录的全链路状态。

    权限：仅管理员。
    查询参数：conversion_or_click_id 支持转化 ID 或 Click ID。
    返回归因、转发、扣量等各环节诊断信息。
    """
    return await diagnostic_handler.diagnose_postback_record(
        conversion_or_click_id, db, current_user
    )


# ====== 更新转化状态接口（融合转化日志功能） ======
@router.put("/postback/conversions/{conversion_id}/status",
            summary="更新转化状态（管理员）")
async def update_conversion_status(
        request: Request,
        conversion_id: int = Path(..., ge=1, description="转化记录ID"),
        status: str = Query(..., description="转化状态（Approved/Pending）"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    手动更新转化记录状态。

    权限：仅管理员。
    查询参数：status 仅允许 Approved 或 Pending。
    变更后写审计日志记录新状态。
    """
    result = await conversion_handler.update_conversion_status(
        conversion_id, status, db, current_user
    )
    await log_update(
        db=db,
        user=current_user,
        resource_type="POSTBACK_CONVERSION",
        resource_id=conversion_id,
        resource_name=f"转化-{conversion_id}",
        request=request,
        details={"status": status},
    )
    await commit_audit_log(db)
    return result


# ====== 待确认转化记录管理接口 ======
@router.get("/postback/pending-conversions",
            summary="查询待确认 Postback 转化记录（管理员）")
async def get_pending_postback_conversions(
        platform: Optional[str] = Query(None, description="平台名称"),
        request_ip: Optional[str] = Query(None, description="请求IP地址"),
        status: Optional[str] = Query(None, description="状态：pending/approved/rejected"),
        start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=1000, description="每页数量"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    分页查询待确认（Pending）Postback 转化记录。

    权限：仅管理员。
    筛选：平台、请求 IP、状态（pending/approved/rejected）、日期范围。
    用于人工审核无法自动归因的转化回调。
    """
    return await pending_handler.get_pending_postback_conversions(
        platform, request_ip, status, start_date, end_date, page, page_size, db, current_user
    )


@router.post("/postback/pending-conversions/{pending_id}/approve",
             summary="批准待确认转化记录（管理员）")
async def approve_pending_conversion(
        request: Request,
        pending_id: int = Path(..., ge=1, description="待确认记录ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    批准待确认转化记录，将其转为正式转化。

    权限：仅管理员。
    批准后触发下游转发与通知；操作写入审计日志。
    """
    result = await pending_handler.approve_pending_conversion(
        pending_id, db, current_user
    )
    conversion_id = result.data.id if result.data else None
    await log_user_action(
        db=db,
        action_type="ACTIVATE",
        user=current_user,
        resource_type="POSTBACK_PENDING_CONVERSION",
        resource_id=pending_id,
        resource_name=f"待确认转化-{pending_id}",
        request=request,
        details={"conversion_id": conversion_id, "action": "approve"},
    )
    await commit_audit_log(db)
    return result


@router.post("/postback/pending-conversions/{pending_id}/reject",
             summary="拒绝待确认转化记录（管理员）")
async def reject_pending_conversion(
        request: Request,
        pending_id: int = Path(..., ge=1, description="待确认记录ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    拒绝待确认转化记录。

    权限：仅管理员。
    拒绝后不再触发下游转发；操作写入审计日志。
    """
    result = await pending_handler.reject_pending_conversion(
        pending_id, db, current_user
    )
    await log_user_action(
        db=db,
        action_type="DEACTIVATE",
        user=current_user,
        resource_type="POSTBACK_PENDING_CONVERSION",
        resource_id=pending_id,
        resource_name=f"待确认转化-{pending_id}",
        request=request,
        details={"action": "reject"},
    )
    await commit_audit_log(db)
    return result


@router.get("/postback/check-duplicates",
            summary="检查重复的转化记录（管理员）")
async def check_duplicate_conversions(
        platform: Optional[str] = Query(None, description="平台名称（可选）"),
        conversion_id: Optional[str] = Query(None, description="转化ID（可选）"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    检查可能重复的转化记录。

    权限：仅管理员。
    可按平台、转化 ID 定位重复组，用于数据清洗与排查。
    """
    return await duplicate_handler.check_duplicate_conversions(
        platform, conversion_id, db, current_user
    )


# ====== 动态平台 PostBack 接收接口 ======
@router.api_route(
    "/postback/{platform}",
    methods=["GET", "POST"],
    summary="接收任意平台的 PostBack 回调（支持 GET 和 POST，接收任意参数）"
)
async def receive_postback(
        request: Request,
        platform: str,
        db: AsyncSession = Depends(get_db)
):
    """
    接收上游广告主的 Postback 转化回调（外部入口）。

    权限：无需登录；通过 IP 白名单与平台标识校验。
    方法：同时支持 GET 与 POST，参数从 query/body 解析。
    路径参数 platform 标识上游平台（如 bft、custom 等）。
    """
    return await receive_handler.receive_postback(
        request, platform, db
    )
