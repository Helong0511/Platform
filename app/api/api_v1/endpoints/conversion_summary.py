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
from app.core.discount.discount_manager import calculate_discount

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/",
            response_model=ResponseBaseSchema[dict],
            summary="获取转化总览统计")
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
    获取转化总览统计（所有登录用户可访问）
    按Offer和Publisher分组统计，返回：
    - Offer ID
    - Offer Name
    - Advertiser（仅管理员可见）
    - Publisher
    - Click: 点击数量
    - Conversion: 转化数量
    - CR (Conversion Rate): 转化率 = Conversion / Click
    - PO: 总支付金额（仅管理员可见）
    - PO（扣价后）: 扣价后的总支付金额（所有用户可见）
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
            conversion_conditions.append(PostbackConversion.product_id == offer_id)
        
        if publisher_id:
            click_conditions.append(Click.publisher_id == publisher_id)
            # PostbackConversion通过click_id关联Click，间接关联publisher_id
            # 需要通过join来过滤
        
        if advertiser_id:
            click_conditions.append(Click.advertiser_id == advertiser_id)
        
        # 统计总点击数量
        click_query = select(func.count(Click.id)).where(and_(*click_conditions))
        click_count = (await db.execute(click_query)).scalar() or 0
        
        # 统计总转化数量
        conversion_query = select(func.count(PostbackConversion.id)).where(and_(*conversion_conditions))
        conversion_count = (await db.execute(conversion_query)).scalar() or 0
        
        # 计算总转化率
        cr = (conversion_count / click_count * 100) if click_count > 0 else 0
        
        # 统计总支付金额（PO）
        po_query = select(func.sum(PostbackConversion.payout)).where(and_(*conversion_conditions))
        po_result = await db.execute(po_query)
        total_po = po_result.scalar() or 0
        
        # 按Offer和Publisher分组统计
        # 先获取所有有点击的Offer-Publisher组合
        click_group_query = select(
            Click.offer_id,
            Click.publisher_id,
            func.count(Click.id).label('click_count')
        ).where(
            and_(*click_conditions)
        ).group_by(Click.offer_id, Click.publisher_id)
        
        click_group_result = await db.execute(click_group_query)
        click_groups = click_group_result.all()
        
        # 构建统计列表
        stats_list = []
        stats_dict = {}  # 用于快速查找，key为(offer_id, publisher_id)
        
        # 处理点击数据
        for offer_id_val, publisher_id_val, click_count_val in click_groups:
            if not offer_id_val or not publisher_id_val:
                continue
            
            key = (offer_id_val, publisher_id_val)
            stats_dict[key] = {
                "offer_id": offer_id_val,
                "publisher_id": publisher_id_val,
                "click_count": click_count_val,
                "conversion_count": 0,
                "po": 0.0,
                "po_after_discount": 0.0
            }
        
        # 获取所有转化记录，按product_id和关联的publisher_id分组
        # 需要通过click_id关联Click表来获取publisher_id
        from sqlalchemy.orm import aliased
        click_alias = aliased(Click)
        
        conversion_group_query = select(
            func.coalesce(PostbackConversion.product_id, click_alias.offer_id).label("offer_id"),
            click_alias.publisher_id,
            func.count(PostbackConversion.id).label('conversion_count'),
            func.sum(PostbackConversion.payout).label('total_po')
        ).outerjoin(
            click_alias, PostbackConversion.click_id == click_alias.click_id
        ).where(
            and_(*conversion_conditions)
        ).group_by(func.coalesce(PostbackConversion.product_id, click_alias.offer_id), click_alias.publisher_id)
        
        if publisher_id:
            conversion_group_query = conversion_group_query.where(click_alias.publisher_id == publisher_id)
        
        conversion_group_result = await db.execute(conversion_group_query)
        conversion_groups = conversion_group_result.all()
        
        # 处理转化数据
        for product_id_val, pub_id_val, conv_count_val, total_po_val in conversion_groups:
            # 允许 offer 为空（未关联产品/点击），使用占位 0
            safe_offer_id = product_id_val if product_id_val is not None else 0
            # 允许没有publisher_id的转化（click_id为空或未匹配到点击），使用占位 0
            safe_pub_id = pub_id_val if pub_id_val is not None else 0
            
            key = (safe_offer_id, safe_pub_id)
            if key not in stats_dict:
                stats_dict[key] = {
                    "offer_id": safe_offer_id,
                    "publisher_id": safe_pub_id,
                    "click_count": 0,
                    "conversion_count": 0,
                    "po": 0.0,
                    "po_after_discount": 0.0,
                    "publisher_missing": pub_id_val is None,
                    "offer_missing": product_id_val is None
                }
            else:
                # 标记如果当前组合缺失publisher
                stats_dict[key]["publisher_missing"] = pub_id_val is None
                stats_dict[key]["offer_missing"] = product_id_val is None
            
            stats_dict[key]["conversion_count"] = conv_count_val
            stats_dict[key]["po"] = float(total_po_val) if total_po_val else 0.0
        
        # 计算PO（扣价后）和填充其他信息
        for key, stat in stats_dict.items():
            offer_id_val, publisher_id_val = key
            
            # 获取Offer信息
            offer_name = None
            advertiser = None
            advertiser_id = None
            if offer_id_val:
                offer_result = await db.execute(
                    select(Offer).where(Offer.id == offer_id_val)
                )
                offer = offer_result.scalars().first()
                # 如果找不到Offer，使用占位信息（可能是product_id与offer_id未映射）
                if not offer:
                    offer_name = f"未找到Offer(ID={offer_id_val})"
                else:
                    offer_name = offer.offer_name
                    advertiser_result = await db.execute(
                        select(Advertiser).where(Advertiser.id == offer.advertiser_id)
                    )
                    advertiser = advertiser_result.scalars().first()
                    advertiser_id = offer.advertiser_id
            else:
                offer_name = "未关联Offer"
            
            # 获取Publisher信息
            publisher = None
            if publisher_id_val:
                publisher_result = await db.execute(
                    select(Publisher).where(Publisher.id == publisher_id_val)
                )
                publisher = publisher_result.scalars().first()
            
            # 没有关联渠道时，使用占位名称
            publisher_name = publisher.publisher_name if publisher else "未关联渠道"
            
            # 计算PO（扣价后）
            # 需要获取该组合下的所有转化记录来计算扣价后的金额
            # 使用join因为我们已经在前面过滤了有publisher_id的记录
            po_after_discount = 0.0
            if publisher_id_val:
                conversions_query = select(PostbackConversion).join(
                    click_alias, PostbackConversion.click_id == click_alias.click_id
                ).where(
                    and_(
                        or_(
                            PostbackConversion.product_id == offer_id_val,
                            and_(PostbackConversion.product_id.is_(None), click_alias.offer_id == offer_id_val)
                        ),
                        click_alias.publisher_id == publisher_id_val,
                        *conversion_conditions[:2]
                    )
                )
                
                conversions_result = await db.execute(conversions_query)
                conversions = conversions_result.scalars().all()
                
                for conversion in conversions:
                    if conversion.payout:
                        final_payout, _, _ = await calculate_discount(
                            db=db,
                            offer_id=offer_id_val if offer_id_val else 0,
                            publisher_id=publisher_id_val,
                            original_payout=conversion.payout
                        )
                        po_after_discount += final_payout
            else:
                # 没有关联渠道，无法计算扣量，使用原始PO
                po_after_discount = stat["po"]
            
            # 计算CR
            cr_val = (stat["conversion_count"] / stat["click_count"] * 100) if stat["click_count"] > 0 else 0
            
            stats_list.append({
                "offer_id": offer_id_val,
                "offer_name": offer_name,
                "advertiser_id": advertiser_id,
                "advertiser_name": advertiser.advertiser_name if advertiser else None,
                "publisher_id": publisher_id_val,
                "publisher_name": publisher_name,
                "click_count": stat["click_count"],
                "conversion_count": stat["conversion_count"],
                "cr": round(cr_val, 2),
                "po": stat["po"],
                "po_after_discount": round(po_after_discount, 2)
            })
        
        # 按点击数量排序
        stats_list.sort(key=lambda x: x['click_count'], reverse=True)
        
        summary = {
            "total_clicks": click_count,
            "total_conversions": conversion_count,
            "cr": round(cr, 2),
            "total_po": float(total_po),
            "stats_list": stats_list,
            "start_date": start_date or (start_datetime.strftime("%Y-%m-%d")),
            "end_date": end_date or (end_datetime.strftime("%Y-%m-%d"))
        }
        
        return ResponseBaseSchema.success(data=summary)
    except Exception as e:
        logger.error(f"获取转化总览统计失败: {str(e)}", exc_info=True)
        raise


@router.get("/by-offer",
            response_model=ResponseBaseSchema[list],
            summary="按Offer统计")
async def get_summary_by_offer(
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """按Offer统计转化数据（所有登录用户可访问）"""
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
                "offer_id": offer.id,
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

