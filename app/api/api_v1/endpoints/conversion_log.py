"""
转化日志 API（增强版，支持CPL系统）
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.models import User, PostbackConversion, Click, Offer, Publisher, Advertiser
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list],
            summary="获取转化日志列表（增强版）",
            dependencies=[Depends(require_admin)])
async def get_conversion_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    click_id: Optional[str] = Query(None, description="Click ID过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
    conversion_status: Optional[str] = Query(None, description="转化状态过滤（Approved/Pending）"),
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取转化日志列表（增强版，支持CPL系统筛选）
    仅管理员
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
        
        # 构建查询条件
        # 如果需要通过 Click 表筛选 publisher_id 或 advertiser_id，需要 JOIN
        need_join_click = publisher_id is not None or advertiser_id is not None
        
        if need_join_click:
            # 需要 JOIN Click 表来筛选 publisher_id 或 advertiser_id
            query = select(PostbackConversion).join(Click, PostbackConversion.click_id == Click.click_id)
        else:
            query = select(PostbackConversion)
        
        conditions = []
        
        if click_id:
            # PostbackConversion 表已有 click_id 字段和索引，直接查询
            conditions.append(PostbackConversion.click_id == click_id)
        
        if offer_id:
            # 注意：PostbackConversion 使用 product_id，需要建立映射
            conditions.append(PostbackConversion.product_id == offer_id)
        
        if publisher_id:
            # 通过 Click 表筛选 publisher_id
            conditions.append(Click.publisher_id == publisher_id)
        
        if advertiser_id:
            # 通过 Click 表筛选 advertiser_id
            conditions.append(Click.advertiser_id == advertiser_id)
        
        if conversion_status:
            # 通过 conversion_status 字段查询
            if hasattr(PostbackConversion, 'conversion_status'):
                conditions.append(PostbackConversion.conversion_status == conversion_status)
        
        if start_datetime:
            conditions.append(PostbackConversion.created_at >= start_datetime)
        if end_datetime:
            conditions.append(PostbackConversion.created_at <= end_datetime)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 总数（使用相同的查询条件）
        total_query = select(func.count(PostbackConversion.id))
        if need_join_click:
            total_query = total_query.select_from(
                PostbackConversion.__table__.join(Click.__table__, PostbackConversion.click_id == Click.click_id)
            )
        else:
            total_query = total_query.select_from(PostbackConversion.__table__)
        
        if conditions:
            total_query = total_query.where(and_(*conditions))
        
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0
        
        # 分页
        query = query.order_by(PostbackConversion.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        conversions = result.scalars().all()
        
        # 批量加载Click记录（优化N+1查询）
        click_ids = [conv.click_id for conv in conversions if hasattr(conv, 'click_id') and conv.click_id]
        clicks_map = {}
        if click_ids:
            clicks_result = await db.execute(
                select(Click).where(Click.click_id.in_(click_ids))
            )
            clicks = clicks_result.scalars().all()
            clicks_map = {click.click_id: click for click in clicks}
        
        # 批量加载关联的Offer、Publisher、Advertiser（进一步优化）
        offer_ids = set()
        publisher_ids = set()
        advertiser_ids = set()
        for click in clicks_map.values():
            if click.offer_id:
                offer_ids.add(click.offer_id)
            if click.publisher_id:
                publisher_ids.add(click.publisher_id)
            if click.advertiser_id:
                advertiser_ids.add(click.advertiser_id)
        
        offers_map = {}
        if offer_ids:
            offers_result = await db.execute(
                select(Offer).where(Offer.id.in_(offer_ids))
            )
            offers = offers_result.scalars().all()
            offers_map = {offer.id: offer for offer in offers}
        
        publishers_map = {}
        if publisher_ids:
            publishers_result = await db.execute(
                select(Publisher).where(Publisher.id.in_(publisher_ids))
            )
            publishers = publishers_result.scalars().all()
            publishers_map = {publisher.id: publisher for publisher in publishers}
        
        advertisers_map = {}
        if advertiser_ids:
            advertisers_result = await db.execute(
                select(Advertiser).where(Advertiser.id.in_(advertiser_ids))
            )
            advertisers = advertisers_result.scalars().all()
            advertisers_map = {advertiser.id: advertiser for advertiser in advertisers}
        
        # 构建返回数据
        log_list = []
        for conv in conversions:
            # 从批量加载的map中获取Click记录
            click_record = None
            if hasattr(conv, 'click_id') and conv.click_id:
                click_record = clicks_map.get(conv.click_id)
            
            # 从批量加载的map中获取关联信息
            offer_name = None
            publisher_name = None
            advertiser_name = None
            click_time = None
            
            if click_record:
                click_time = click_record.click_time
                if click_record.offer_id:
                    offer = offers_map.get(click_record.offer_id)
                    if offer:
                        offer_name = offer.offer_name
                
                if click_record.publisher_id:
                    publisher = publishers_map.get(click_record.publisher_id)
                    if publisher:
                        publisher_name = publisher.publisher_name
                
                if click_record.advertiser_id:
                    advertiser = advertisers_map.get(click_record.advertiser_id)
                    if advertiser:
                        advertiser_name = advertiser.advertiser_name
            
            log_data = {
                "id": conv.id,
                "click_id": getattr(conv, 'click_id', None) or (click_record.click_id if click_record else None),
                "click_time": click_time.isoformat() if click_time else None,
                "conversion_time": conv.created_at.isoformat() if conv.created_at else None,
                "conversion_status": getattr(conv, 'conversion_status', 'Pending'),
                "offer_id": click_record.offer_id if click_record else None,
                "offer_name": offer_name,
                "publisher_id": click_record.publisher_id if click_record else None,
                "publisher_name": publisher_name,
                "advertiser_id": click_record.advertiser_id if click_record else None,
                "advertiser_name": advertiser_name,
                "ip": click_record.ip if click_record else conv.ip,
                "device": click_record.device if click_record else None,
                "country": click_record.country if click_record else None,
                "platform": conv.platform,
                "payout": float(conv.payout) if conv.payout else None,
                "event_name": conv.event_name,
                "created_at": conv.created_at.isoformat() if conv.created_at else None
            }
            log_list.append(log_data)
        
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
            summary="更新转化状态",
            dependencies=[Depends(require_admin)])
async def update_conversion_status(
    conversion_id: int,
    status: str = Query(..., description="转化状态（Approved/Pending）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新转化状态（仅管理员）"""
    try:
        result = await db.execute(
            select(PostbackConversion).where(PostbackConversion.id == conversion_id)
        )
        conversion = result.scalars().first()
        
        if not conversion:
            from app.core.exceptions import raise_api_exception
            from app.core.errors import ErrorCode
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"转化记录ID {conversion_id} 不存在"
            )
        
        # 更新转化状态
        if hasattr(conversion, 'conversion_status'):
            conversion.conversion_status = status
            await db.commit()
            await db.refresh(conversion)
            logger.info(f"转化状态已更新: conversion_id={conversion_id}, status={status}")
        else:
            logger.warning(f"PostbackConversion 模型缺少 conversion_status 字段")
        
        return ResponseBaseSchema.success(data={"message": "状态更新成功"})
    except Exception as e:
        logger.error(f"更新转化状态失败: {str(e)}", exc_info=True)
        raise

