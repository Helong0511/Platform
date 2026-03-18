"""
短链接访问记录 API（clicks 表数据）
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.dependencies import get_click_service
from app.core.security import get_current_user, require_admin
from app.models.models import User
from app.schemas.base import PaginatedResponseBaseSchema
from app.services.click_service import ClickService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list],
            summary="获取短链接访问记录列表",
            dependencies=[Depends(require_admin)])
async def get_clicks(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        click_id: Optional[str] = Query(None, description="Click ID过滤"),
        offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
        publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
        advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
        short_link_id: Optional[int] = Query(None, description="短链接ID过滤"),
        ip: Optional[str] = Query(None, description="IP地址过滤"),
        country: Optional[str] = Query(None, description="国家过滤"),
        start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取短链接访问记录列表（clicks 表数据，已重构使用服务层）
    仅管理员可访问
    
    优化说明：
    - 如果没有提供日期范围，默认查询最近7天的数据（优化性能）
    - 最大查询范围限制为90天（防止查询过大数据量）
    """
    # 使用服务层（业务逻辑在ClickService中）
    click_service: ClickService = await get_click_service(db)

    try:
        # 调用服务层获取点击记录列表（服务层会处理查询、过滤、分页、日期验证等）
        click_list, total = await click_service.get_clicks(
            page=page,
            page_size=page_size,
            click_id=click_id,
            offer_id=offer_id,
            publisher_id=publisher_id,
            advertiser_id=advertiser_id,
            short_link_id=short_link_id,
            ip=ip,
            country=country,
            start_date=start_date,
            end_date=end_date
        )

        return PaginatedResponseBaseSchema.success(
            data=click_list,
            total=total,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error(f"获取短链接访问记录列表失败: {str(e)}", exc_info=True)
        raise
