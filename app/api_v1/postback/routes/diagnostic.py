"""Postback 诊断路由。"""
from fastapi import APIRouter, Query, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.models.models import User
from app.api_v1.postback.audit import audit_postback_pii_read

from ..handlers import diagnostic_handler

router = APIRouter()


@router.get("/postback/diagnose", summary="诊断 PostBack 记录问题（管理员）")
async def diagnose_postback_record(
    request: Request,
    conversion_or_click_id: str = Query(..., description="转化ID或点击ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await diagnostic_handler.diagnose_postback_record(
        conversion_or_click_id, db, current_user,
    )
    await audit_postback_pii_read(
        db=db,
        current_user=current_user,
        request=request,
        resource_name="conversion_diagnostic",
        details={"filter_fields_present": ["conversion_or_click_id"]},
    )
    return result
