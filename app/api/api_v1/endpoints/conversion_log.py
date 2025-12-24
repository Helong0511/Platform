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
        # 使用 LEFT JOIN 关联 Click 表以支持通过 Click 字段过滤
        query = select(PostbackConversion, Click, Offer, Publisher, Advertiser).outerjoin(
            Click, PostbackConversion.click_id == Click.click_id
        ).outerjoin(
            Offer, Click.offer_id == Offer.id
        ).outerjoin(
            Publisher, Click.publisher_id == Publisher.id
        ).outerjoin(
            Advertiser, Click.advertiser_id == Advertiser.id
        )
        
        conditions = []
        
        # Click ID 过滤：直接使用 PostbackConversion.click_id 字段
        if click_id:
            conditions.append(PostbackConversion.click_id == click_id)
        
        # Offer ID 过滤：通过 Click 表关联
        if offer_id:
            conditions.append(Click.offer_id == offer_id)
        
        # Publisher ID 过滤：通过 Click 表关联
        if publisher_id:
            conditions.append(Click.publisher_id == publisher_id)
        
        # Advertiser ID 过滤：通过 Click 表关联
        if advertiser_id:
            conditions.append(Click.advertiser_id == advertiser_id)
        
        # 转化状态过滤
        if conversion_status:
            if hasattr(PostbackConversion, 'conversion_status'):
                # 验证状态值
                if conversion_status not in ['Approved', 'Pending']:
                    from app.core.exceptions import raise_api_exception
                    from app.core.errors import ErrorCode
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMS,
                        detail=f"无效的转化状态: {conversion_status}，只支持 Approved 或 Pending"
                    )
                conditions.append(PostbackConversion.conversion_status == conversion_status)
        
        # 日期范围过滤
        if start_datetime:
            conditions.append(PostbackConversion.created_at >= start_datetime)
        if end_datetime:
            conditions.append(PostbackConversion.created_at <= end_datetime)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 总数查询：使用相同的条件，但只计数 PostbackConversion
        # 对于需要通过 Click 表过滤的条件，需要 JOIN
        count_query = select(func.count(PostbackConversion.id))
        
        # 构建计数查询的条件
        count_conditions = []
        needs_click_join = False
        
        if click_id:
            count_conditions.append(PostbackConversion.click_id == click_id)
        
        if offer_id or publisher_id or advertiser_id:
            needs_click_join = True
            count_query = count_query.select_from(
                PostbackConversion.outerjoin(Click, PostbackConversion.click_id == Click.click_id)
            )
            if offer_id:
                count_conditions.append(Click.offer_id == offer_id)
            if publisher_id:
                count_conditions.append(Click.publisher_id == publisher_id)
            if advertiser_id:
                count_conditions.append(Click.advertiser_id == advertiser_id)
        else:
            count_query = count_query.select_from(PostbackConversion)
        
        if conversion_status and hasattr(PostbackConversion, 'conversion_status'):
            count_conditions.append(PostbackConversion.conversion_status == conversion_status)
        
        if start_datetime:
            count_conditions.append(PostbackConversion.created_at >= start_datetime)
        if end_datetime:
            count_conditions.append(PostbackConversion.created_at <= end_datetime)
        
        if count_conditions:
            count_query = count_query.where(and_(*count_conditions))
        
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页
        query = query.order_by(PostbackConversion.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        rows = result.unique().all()
        
        # 构建返回数据
        log_list = []
        for row in rows:
            # 解构查询结果
            conv = row[0]  # PostbackConversion
            click_record = row[1] if len(row) > 1 else None  # Click
            offer = row[2] if len(row) > 2 else None  # Offer
            publisher = row[3] if len(row) > 3 else None  # Publisher
            advertiser = row[4] if len(row) > 4 else None  # Advertiser
            
            log_data = {
                "id": conv.id,
                "click_id": conv.click_id if hasattr(conv, 'click_id') and conv.click_id else (click_record.click_id if click_record else None),
                "click_time": click_record.click_time.isoformat() if click_record and click_record.click_time else (conv.click_time.isoformat() if hasattr(conv, 'click_time') and conv.click_time else None),
                "conversion_time": conv.created_at.isoformat() if conv.created_at else None,
                "conversion_status": getattr(conv, 'conversion_status', 'Pending'),
                "offer_id": click_record.offer_id if click_record else None,
                "offer_name": offer.offer_name if offer else None,
                "publisher_id": click_record.publisher_id if click_record else None,
                "publisher_name": publisher.publisher_name if publisher else None,
                "advertiser_id": click_record.advertiser_id if click_record else None,
                "advertiser_name": advertiser.advertiser_name if advertiser else None,
                "ip": click_record.ip if click_record else (conv.ip if hasattr(conv, 'ip') else None),
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
        # 验证状态值
        valid_statuses = ['Approved', 'Pending']
        if status not in valid_statuses:
            from app.core.exceptions import raise_api_exception
            from app.core.errors import ErrorCode
            raise_api_exception(
                ErrorCode.INVALID_PARAMS,
                detail=f"无效的转化状态: {status}，只支持 {', '.join(valid_statuses)}"
            )
        
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
            old_status = conversion.conversion_status
            conversion.conversion_status = status
            await db.commit()
            await db.refresh(conversion)
            logger.info(f"转化状态已更新: conversion_id={conversion_id}, old_status={old_status}, new_status={status}")
        else:
            logger.warning(f"PostbackConversion 模型缺少 conversion_status 字段")
            from app.core.exceptions import raise_api_exception
            from app.core.errors import ErrorCode
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="转化状态字段不存在，请检查数据库模型"
            )
        
        return ResponseBaseSchema.success(data={"message": "状态更新成功", "conversion_id": conversion_id, "status": status})
    except Exception as e:
        logger.error(f"更新转化状态失败: {str(e)}", exc_info=True)
        raise

