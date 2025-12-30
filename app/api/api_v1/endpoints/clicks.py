"""
短链接访问记录 API（clicks 表数据）
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from sqlalchemy.orm import joinedload

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.models import User, Click, Offer, Publisher, Advertiser, ShortLink
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list],
            summary="获取短链接访问记录列表",
            dependencies=[Depends(require_admin)])
async def get_clicks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
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
    获取短链接访问记录列表（clicks 表数据）
    仅管理员可访问
    """
    try:
        # 解析日期
        start_datetime = None
        end_datetime = None
        if start_date:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end_date:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
        
        # 构建查询 - 使用 joinedload 预加载关联数据，避免 N+1 查询
        query = select(Click).options(
            joinedload(Click.offer),
            joinedload(Click.publisher),
            joinedload(Click.advertiser),
            joinedload(Click.short_link)
        )
        
        conditions = []
        
        if click_id:
            conditions.append(Click.click_id == click_id)
        
        if offer_id:
            conditions.append(Click.offer_id == offer_id)
        
        if publisher_id:
            conditions.append(Click.publisher_id == publisher_id)
        
        if advertiser_id:
            conditions.append(Click.advertiser_id == advertiser_id)
        
        if short_link_id:
            conditions.append(Click.short_link_id == short_link_id)
        
        if ip:
            conditions.append(Click.ip.like(f"%{ip}%"))
        
        if country:
            conditions.append(Click.country == country)
        
        if start_datetime:
            conditions.append(Click.click_time >= start_datetime)
        if end_datetime:
            conditions.append(Click.click_time <= end_datetime)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 计算总数
        count_query = select(func.count(Click.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页和排序
        query = query.order_by(Click.click_time.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        clicks = result.unique().scalars().all()
        
        # 构建返回数据
        click_list = []
        for click in clicks:
            click_data = {
                "id": click.id,
                "click_id": click.click_id,
                "click_time": click.click_time.isoformat() if click.click_time else None,
                "ip": click.ip,
                "device": click.device,
                "country": click.country,
                "user_agent": click.user_agent,
                "referer": click.referer,
                "conversion_id": click.conversion_id,
                "created_at": click.created_at.isoformat() if click.created_at else None,
                "offer_id": click.offer_id,
                "offer_name": click.offer.offer_name if click.offer else None,
                "publisher_id": click.publisher_id,
                "publisher_name": click.publisher.publisher_name if click.publisher else None,
                "advertiser_id": click.advertiser_id,
                "advertiser_name": click.advertiser.advertiser_name if click.advertiser else None,
                "short_link_id": click.short_link_id,
                "short_code": click.short_link.short_code if click.short_link else None,
                "short_link_url": click.short_link.original_url if click.short_link else None,
            }
            click_list.append(click_data)
        
        return PaginatedResponseBaseSchema.success(
            data=click_list,
            total=total,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error(f"获取短链接访问记录列表失败: {str(e)}", exc_info=True)
        raise

