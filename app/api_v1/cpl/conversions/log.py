"""
转化日志 API（已废弃，功能已融合到 Postback 管理 API）
保留此 API 以保持向后兼容性，建议使用 /api/v1/postback/conversions 接口
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.dependencies import get_conversion_log_service
from app.core.security import get_current_user, require_admin
from app.models.models import User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.services.cpl.conversion_log_service import ConversionLogService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list],
            summary="获取转化日志列表（已废弃，请使用 /api/v1/postback/conversions）",
            deprecated=True,
            dependencies=[Depends(require_admin)])
async def get_conversion_logs(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        click_id: Optional[str] = Query(None, description="Click ID过滤"),
        offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
        publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        conversion_status: Optional[str] = Query(None,
                                                 description="转化状态过滤（Pending/Approved/CapReached/OfferInactive/ClickExpired）"),
        start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取转化日志列表（已废弃）
    
    注意：此接口已废弃，功能已融合到 Postback 管理 API 中。
    请使用 /api/v1/postback/conversions 接口，它支持所有转化日志的筛选条件。
    仅管理员
    """
    # 使用服务层（业务逻辑在ConversionLogService中）
    conversion_log_service: ConversionLogService = await get_conversion_log_service(db)

    try:
        # 调用服务层获取转化日志列表（服务层会处理查询、过滤、分页、批量加载等）
        log_list, total = await conversion_log_service.get_conversion_logs(
            page=page,
            page_size=page_size,
            click_id=click_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
            conversion_status=conversion_status,
            start_date=start_date,
            end_date=end_date
        )

        return PaginatedResponseBaseSchema.success(
            data=log_list,
            total=total,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error(f"获取转化日志列表失败: {str(e)}", exc_info=True)
        raise


@router.put("/{conversion_id}/status",
            response_model=ResponseBaseSchema[dict],
            summary="更新转化状态（已废弃，请使用 /api/v1/postback/conversions/{conversion_id}/status）",
            deprecated=True,
            dependencies=[Depends(require_admin)])
async def update_conversion_status(
        conversion_id: int,
        status: str = Query(..., description="转化状态（Approved/Pending）"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    更新转化状态（已废弃）
    
    注意：此接口已废弃，功能已融合到 Postback 管理 API 中。
    请使用 /api/v1/postback/conversions/{conversion_id}/status 接口。
    仅管理员
    """
    # 使用服务层（业务逻辑在ConversionLogService中）
    conversion_log_service: ConversionLogService = await get_conversion_log_service(db)

    try:
        # 调用服务层更新转化状态（服务层会处理验证和更新）
        await conversion_log_service.update_conversion_status(conversion_id, status, current_user)

        return ResponseBaseSchema.success(data={"message": "状态更新成功"})
    except Exception as e:
        logger.error(f"更新转化状态失败: {str(e)}", exc_info=True)
        raise
