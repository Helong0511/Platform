"""Postback 诊断路由。"""
from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.models.models import User

from ..handlers import diagnostic_handler

router = APIRouter()


@router.get("/postback/diagnose", summary="诊断 PostBack 记录问题（管理员）")
async def diagnose_postback_record(
    conversion_or_click_id: str = Query(..., description="转化ID或点击ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await diagnostic_handler.diagnose_postback_record(
        conversion_or_click_id, db, current_user,
    )
