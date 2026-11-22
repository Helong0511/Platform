"""Postback 待确认转化路由。"""
from typing import Optional

from fastapi import APIRouter, Query, Depends, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.security import require_admin
from app.models.models import User
from app.api_v1.postback.audit import audit_postback_pii_read

from ..handlers import pending_handler

router = APIRouter()


@router.get("/postback/pending-conversions", summary="查询待确认 Postback 转化记录（管理员）")
async def get_pending_postback_conversions(
    request: Request,
    platform: Optional[str] = Query(None, description="平台名称"),
    request_ip: Optional[str] = Query(None, description="请求IP地址"),
    status: Optional[str] = Query(None, description="状态：pending/approved/rejected"),
    start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=1000, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await pending_handler.get_pending_postback_conversions(
        platform, request_ip, status, start_date, end_date, page, page_size, db, current_user,
    )
    await audit_postback_pii_read(
        db=db,
        current_user=current_user,
        request=request,
        resource_name="pending_conversion_list",
        details={
            "filter_fields_present": [
                name
                for name, value in {
                    "platform": platform,
                    "request_ip": request_ip,
                    "status": status,
                    "start_date": start_date,
                    "end_date": end_date,
                }.items()
                if value is not None and value != ""
            ],
            "page": page,
            "page_size": page_size,
        },
    )
    return result


@router.post("/postback/pending-conversions/{pending_id}/approve", summary="批准待确认转化记录（管理员）")
async def approve_pending_conversion(
    request: Request,
    pending_id: int = Path(..., ge=1, description="待确认记录ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await pending_handler.approve_pending_conversion(
        pending_id, db, current_user,
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


@router.post("/postback/pending-conversions/{pending_id}/reject", summary="拒绝待确认转化记录（管理员）")
async def reject_pending_conversion(
    request: Request,
    pending_id: int = Path(..., ge=1, description="待确认记录ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await pending_handler.reject_pending_conversion(
        pending_id, db, current_user,
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
