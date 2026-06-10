from typing import Optional

from fastapi import APIRouter, Query, Depends, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_update, commit_audit_log
from app.core.database import get_db
from app.core.security import require_admin
from app.models.models import User

from ..handlers import conversion_handler, stats_handler, duplicate_handler

router = APIRouter()


@router.get("/postback/conversions", summary="查询 PostBack 转化记录（管理员，已融合转化日志功能）")
async def get_postback_conversions(
    request: Request,
    platform: Optional[str] = Query(None, description="平台名称"),
    product_id: Optional[int] = Query(None, description="产品ID"),
    client_id: Optional[int] = Query(None, description="客户ID"),
    conversion_or_click_id: Optional[str] = Query(None, description="转化ID或点击ID"),
    click_id: Optional[str] = Query(None, description="Click ID过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
    conversion_status: Optional[str] = Query(None, description="转化状态过滤"),
    start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=1000, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await conversion_handler.get_postback_conversions(
        request, platform, product_id, client_id, conversion_or_click_id,
        click_id, offer_id, publisher_id, advertiser_id, conversion_status,
        start_date, end_date, page, page_size, db, current_user,
    )


@router.get("/postback/stats", summary="PostBack 统计信息（管理员）")
async def get_postback_stats(
    request: Request,
    platform: Optional[str] = Query(None, description="平台名称"),
    start_date: Optional[str] = Query(None, description="起始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await stats_handler.get_postback_stats(
        platform=platform,
        start_date=start_date,
        end_date=end_date,
        db=db,
        current_user=current_user,
    )


@router.put("/postback/conversions/{conversion_id}/status", summary="更新转化状态（管理员）")
async def update_conversion_status(
    request: Request,
    conversion_id: int = Path(..., ge=1, description="转化记录ID"),
    status: str = Query(..., description="转化状态（Approved/Pending）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await conversion_handler.update_conversion_status(
        conversion_id, status, db, current_user,
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


@router.get("/postback/check-duplicates", summary="检查重复的转化记录（管理员）")
async def check_duplicate_conversions(
    platform: Optional[str] = Query(None, description="平台名称（可选）"),
    conversion_id: Optional[str] = Query(None, description="转化ID（可选）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await duplicate_handler.check_duplicate_conversions(
        platform, conversion_id, db, current_user,
    )
