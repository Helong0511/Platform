"""
转化总览统计 API
"""
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.models import User, Click, PostbackConversion, Offer, Publisher, Advertiser
from app.schemas.base import ResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/",
            response_model=ResponseBaseSchema[dict],
            summary="获取转化总览统计",
            dependencies=[Depends(require_admin)])
async def get_conversion_summary(
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取转化总览统计（仅管理员）
    统计指标：
    - Click: 点击数量
    - Conversion: 转化数量
    - CR (Conversion Rate): 转化率 = Conversion / Click
    - PO (Payout): 总支付金额
    """
    try:
        # 解析日期
        start_datetime = None
        end_datetime = None
        if start_date:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end_date:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        
        # 如果没有指定日期，默认查询最近30天
        if not start_datetime:
            start_datetime = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_datetime:
            end_datetime = datetime.now(timezone.utc)
        
        # 构建查询条件
        click_conditions = [Click.click_time >= start_datetime, Click.click_time < end_datetime]
        conversion_conditions = [PostbackConversion.created_at >= start_datetime, PostbackConversion.created_at < end_datetime]
        
        if offer_id:
            click_conditions.append(Click.offer_id == offer_id)
            # 注意：PostbackConversion 使用 product_id，需要建立 Offer 和 Product 的映射关系
            # 这里暂时使用 product_id，后续需要根据实际业务逻辑调整
            conversion_conditions.append(PostbackConversion.product_id == offer_id)
        
        if publisher_id:
            click_conditions.append(Click.publisher_id == publisher_id)
        
        if advertiser_id:
            click_conditions.append(Click.advertiser_id == advertiser_id)
            # 如果PostbackConversion表有advertiser_id字段，也需要添加
        
        # 统计点击数量
        click_query = select(func.count(Click.id)).where(and_(*click_conditions))
        click_count = (await db.execute(click_query)).scalar() or 0
        
        # 统计转化数量
        conversion_query = select(func.count(PostbackConversion.id)).where(and_(*conversion_conditions))
        conversion_count = (await db.execute(conversion_query)).scalar() or 0
        
        # 计算转化率
        cr = (conversion_count / click_count * 100) if click_count > 0 else 0
        
        # 统计总支付金额（PO）
        # 注意：这里需要根据实际的PostbackConversion表结构来获取payout字段
        po_query = select(func.sum(PostbackConversion.payout)).where(and_(*conversion_conditions))
        po_result = await db.execute(po_query)
        total_po = po_result.scalar() or 0
        
        # 按Offer统计
        offer_stats = []
        if offer_id:
            # 单个Offer统计
            offer_result = await db.execute(
                select(Offer).where(Offer.id == offer_id)
            )
            offer = offer_result.scalars().first()
            if offer:
                offer_click_count = (await db.execute(
                    select(func.count(Click.id)).where(
                        and_(Click.offer_id == offer_id, *click_conditions[:2])
                    )
                )).scalar() or 0
                
                offer_conversion_count = (await db.execute(
                    select(func.count(PostbackConversion.id)).where(
                        and_(PostbackConversion.product_id == offer_id, *conversion_conditions[:2])
                    )
                )).scalar() or 0
                
                offer_cr = (offer_conversion_count / offer_click_count * 100) if offer_click_count > 0 else 0
                
                offer_po = (await db.execute(
                    select(func.sum(PostbackConversion.payout)).where(
                        and_(PostbackConversion.product_id == offer_id, *conversion_conditions[:2])
                    )
                )).scalar() or 0
                
                offer_stats.append({
                    "offer_id": offer.offer_id,
                    "offer_name": offer.offer_name,
                    "click_count": offer_click_count,
                    "conversion_count": offer_conversion_count,
                    "cr": round(offer_cr, 2),
                    "po": float(offer_po) if offer_po else 0
                })
        else:
            # 所有Offer统计（Top 10）
            offer_click_query = select(
                Click.offer_id,
                func.count(Click.id).label('click_count')
            ).where(
                and_(*click_conditions)
            ).group_by(Click.offer_id).order_by(func.count(Click.id).desc()).limit(10)
            
            offer_click_result = await db.execute(offer_click_query)
            top_offers = offer_click_result.all()
            
            for offer_id_val, click_count_val in top_offers:
                if not offer_id_val:
                    continue
                
                offer_result = await db.execute(
                    select(Offer).where(Offer.id == offer_id_val)
                )
                offer = offer_result.scalars().first()
                if not offer:
                    continue
                
                conversion_count_val = (await db.execute(
                    select(func.count(PostbackConversion.id)).where(
                        and_(PostbackConversion.product_id == offer_id_val, *conversion_conditions[:2])
                    )
                )).scalar() or 0
                
                cr_val = (conversion_count_val / click_count_val * 100) if click_count_val > 0 else 0
                
                po_val = (await db.execute(
                    select(func.sum(PostbackConversion.payout)).where(
                        and_(PostbackConversion.product_id == offer_id_val, *conversion_conditions[:2])
                    )
                )).scalar() or 0
                
                offer_stats.append({
                    "offer_id": offer.offer_id,
                    "offer_name": offer.offer_name,
                    "click_count": click_count_val,
                    "conversion_count": conversion_count_val,
                    "cr": round(cr_val, 2),
                    "po": float(po_val) if po_val else 0
                })
        
        summary = {
            "total_clicks": click_count,
            "total_conversions": conversion_count,
            "cr": round(cr, 2),
            "total_po": float(total_po),
            "offer_stats": offer_stats,
            "start_date": start_date or (start_datetime.strftime("%Y-%m-%d")),
            "end_date": end_date or (end_datetime.strftime("%Y-%m-%d"))
        }
        
        return ResponseBaseSchema.success(data=summary)
    except Exception as e:
        logger.error(f"获取转化总览统计失败: {str(e)}", exc_info=True)
        raise


@router.get("/by-offer",
            response_model=ResponseBaseSchema[list],
            summary="按Offer统计",
            dependencies=[Depends(require_admin)])
async def get_summary_by_offer(
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """按Offer统计转化数据（仅管理员）"""
    try:
        # 解析日期
        start_datetime = None
        end_datetime = None
        if start_date:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end_date:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        
        if not start_datetime:
            start_datetime = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_datetime:
            end_datetime = datetime.now(timezone.utc)
        
        # 获取所有Offer
        offers_result = await db.execute(select(Offer))
        offers = offers_result.scalars().all()
        
        stats_list = []
        for offer in offers:
            click_count = (await db.execute(
                select(func.count(Click.id)).where(
                    and_(
                        Click.offer_id == offer.id,
                        Click.click_time >= start_datetime,
                        Click.click_time < end_datetime
                    )
                )
            )).scalar() or 0
            
            conversion_count = (await db.execute(
                select(func.count(PostbackConversion.id)).where(
                    and_(
                        PostbackConversion.product_id == offer.id,
                        PostbackConversion.created_at >= start_datetime,
                        PostbackConversion.created_at < end_datetime
                    )
                )
            )).scalar() or 0
            
            cr = (conversion_count / click_count * 100) if click_count > 0 else 0
            
            po = (await db.execute(
                select(func.sum(PostbackConversion.payout)).where(
                    and_(
                        PostbackConversion.product_id == offer.id,
                        PostbackConversion.created_at >= start_datetime,
                        PostbackConversion.created_at < end_datetime
                    )
                )
            )).scalar() or 0
            
            stats_list.append({
                "offer_id": offer.offer_id,
                "offer_name": offer.offer_name,
                "click_count": click_count,
                "conversion_count": conversion_count,
                "cr": round(cr, 2),
                "po": float(po) if po else 0
            })
        
        # 按点击数量排序
        stats_list.sort(key=lambda x: x['click_count'], reverse=True)
        
        return ResponseBaseSchema.success(data=stats_list)
    except Exception as e:
        logger.error(f"按Offer统计失败: {str(e)}", exc_info=True)
        raise

