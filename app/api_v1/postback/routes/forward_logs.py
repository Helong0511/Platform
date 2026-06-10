"""Postback 下游转发日志路由。"""
from typing import Optional

from fastapi import APIRouter, Query, Depends, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.security import require_admin
from app.models.models import User

from ..handlers import forward_log_handler

router = APIRouter()


@router.get("/postback/forward-logs", summary="查询 PostBack 下游转发日志（管理员）")
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
    current_user: User = Depends(require_admin),
):
    return await forward_log_handler.get_postback_forward_logs(
        request, conversion_id, product_id, publisher_id, success,
        start_date, end_date, page, page_size, db, current_user,
    )


@router.post("/postback/forward-logs/{forward_log_id}/resend", summary="补发 PostBack 转发（管理员）")
async def resend_postback_forward(
    request: Request,
    forward_log_id: int = Path(..., ge=1, description="转发日志ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await forward_log_handler.resend_postback_forward(
        forward_log_id, db, current_user,
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
