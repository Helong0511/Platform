"""
转化服务层
封装转化相关的业务逻辑和统计查询
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, case
from sqlalchemy.orm import aliased

from app.models.models import (
    PostbackConversion, ClickStats, Offer, Publisher, Advertiser,
    User, UserRole, Client
)
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class ConversionService:
    """转化服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_conversion_summary(
        self,
        current_user: User,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        advertiser_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        获取转化总览统计（优化查询，批量加载关联数据）
        
        Args:
            current_user: 当前用户
            start_date: 开始日期
            end_date: 结束日期
            offer_id: Offer ID过滤
            publisher_id: 渠道ID过滤
            advertiser_id: 广告主ID过滤
        
        Returns:
            Dict: 统计信息
        """
        # 解析日期
        start_datetime = None
        end_datetime = None
        
        if start_date:
            start_datetime = parse_date_to_app_timezone(start_date)
        if end_date:
            end_datetime = parse_date_to_app_timezone(end_date)
            # 结束日期包含整天，所以设置为当天的23:59:59
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
        
        # 权限过滤：客户只能查看自己的数据
        client_publisher_ids = None
        if current_user.role == UserRole.CLIENT:
            client_result = await self.db.execute(
                select(Client.id).where(Client.user_id == current_user.id).limit(1)
            )
            client_id = client_result.scalar_one_or_none()
            if client_id:
                publisher_result = await self.db.execute(
                    select(Publisher.id).where(Publisher.client_id == client_id)
                )
                client_publisher_ids = [p.id for p in publisher_result.scalars().all()]
            else:
                # 客户没有关联的Client记录，返回空统计
                return {
                    "total_conversions": 0,
                    "total_po": 0.0,
                    "total_po_after_discount": 0.0,
                    "by_offer_publisher": []
                }
        
        # 构建查询（优化：使用JOIN减少查询次数）
        query = (
            select(
                ClickStats.offer_id,
                ClickStats.publisher_id,
                func.count(PostbackConversion.id).label('conversion_count'),
                func.sum(PostbackConversion.original_payout).label('total_po')
            )
            .join(
                PostbackConversion,
                PostbackConversion.click_id == ClickStats.click_id
            )
        )
        
        # 添加过滤条件
        conditions = []
        
        if start_datetime:
            conditions.append(PostbackConversion.created_at >= start_datetime)
        if end_datetime:
            conditions.append(PostbackConversion.created_at <= end_datetime)
        if offer_id:
            conditions.append(ClickStats.offer_id == offer_id)
        if publisher_id:
            conditions.append(ClickStats.publisher_id == publisher_id)
        if advertiser_id:
            conditions.append(ClickStats.advertiser_id == advertiser_id)
        if client_publisher_ids is not None:
            conditions.append(ClickStats.publisher_id.in_(client_publisher_ids))
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 按offer_id和publisher_id分组
        query = query.group_by(ClickStats.offer_id, ClickStats.publisher_id)
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # 收集所有需要加载的ID
        offer_ids = set()
        publisher_ids = set()
        advertiser_ids = set()
        
        stats_dict = {}
        for row in rows:
            offer_id_val = row.offer_id
            publisher_id_val = row.publisher_id
            
            if offer_id_val:
                offer_ids.add(offer_id_val)
            if publisher_id_val:
                publisher_ids.add(publisher_id_val)
            
            key = (offer_id_val, publisher_id_val)
            stats_dict[key] = {
                "conversion_count": row.conversion_count or 0,
                "po": float(row.total_po) if row.total_po else 0.0
            }
        
        # 批量加载Offer和Advertiser信息（避免N+1查询）
        offers_map = {}
        advertisers_map = {}
        if offer_ids:
            offers_result = await self.db.execute(
                select(Offer, Advertiser)
                .join(Advertiser, Offer.advertiser_id == Advertiser.id)
                .where(Offer.id.in_(offer_ids))
            )
            for offer, advertiser in offers_result.all():
                offers_map[offer.id] = offer
                advertisers_map[offer.id] = advertiser
        
        # 批量加载Publisher信息
        publishers_map = {}
        if publisher_ids:
            publishers_result = await self.db.execute(
                select(Publisher).where(Publisher.id.in_(publisher_ids))
            )
            for publisher in publishers_result.scalars().all():
                publishers_map[publisher.id] = publisher
        
        # 构建响应数据
        summary_list = []
        total_conversions = 0
        total_po = 0.0
        
        for key, stat in stats_dict.items():
            offer_id_val, publisher_id_val = key
            
            # 获取关联信息（从批量加载的map中获取）
            offer = offers_map.get(offer_id_val) if offer_id_val else None
            advertiser = advertisers_map.get(offer_id_val) if offer_id_val else None
            publisher = publishers_map.get(publisher_id_val) if publisher_id_val else None
            
            summary_list.append({
                "offer_id": offer_id_val,
                "offer_name": offer.offer_name if offer else "未关联Offer",
                "advertiser_id": offer.advertiser_id if offer else None,
                "advertiser_name": advertiser.advertiser_name if advertiser else None,
                "publisher_id": publisher_id_val,
                "publisher_name": publisher.publisher_name if publisher else "未关联渠道",
                "conversion_count": stat["conversion_count"],
                "po": stat["po"]
            })
            
            total_conversions += stat["conversion_count"]
            total_po += stat["po"]
        
        return {
            "total_conversions": total_conversions,
            "total_po": total_po,
            "by_offer_publisher": summary_list
        }
    
    async def get_conversions_by_offer(
        self,
        current_user: User,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        按Offer统计转化数据（优化查询）
        
        Args:
            current_user: 当前用户
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            List: 按Offer的统计列表
        """
        # 解析日期
        start_datetime = None
        end_datetime = None
        
        if start_date:
            start_datetime = parse_date_to_app_timezone(start_date)
        if end_date:
            end_datetime = parse_date_to_app_timezone(end_date)
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
        
        # 权限过滤
        client_publisher_ids = None
        if current_user.role == UserRole.CLIENT:
            client_result = await self.db.execute(
                select(Client.id).where(Client.user_id == current_user.id).limit(1)
            )
            client_id = client_result.scalar_one_or_none()
            if client_id:
                publisher_result = await self.db.execute(
                    select(Publisher.id).where(Publisher.client_id == client_id)
                )
                client_publisher_ids = [p.id for p in publisher_result.scalars().all()]
            else:
                return []
        
        # 获取所有激活的Offer（批量加载）
        offer_query = select(Offer).where(
            and_(
                Offer.is_active == True,
                Offer.status == 'Active'
            )
        )
        offers_result = await self.db.execute(offer_query)
        offers = offers_result.scalars().all()
        
        if not offers:
            return []
        
        offer_ids = [offer.id for offer in offers]
        
        # 批量查询点击统计（优化：一次查询获取所有数据）
        click_stats_query = select(
            ClickStats.offer_id,
            func.count(ClickStats.click_id).label('click_count')
        ).where(ClickStats.offer_id.in_(offer_ids))
        
        if start_datetime:
            click_stats_query = click_stats_query.where(
                ClickStats.click_time >= start_datetime
            )
        if end_datetime:
            click_stats_query = click_stats_query.where(
                ClickStats.click_time <= end_datetime
            )
        if client_publisher_ids is not None:
            click_stats_query = click_stats_query.where(
                ClickStats.publisher_id.in_(client_publisher_ids)
            )
        
        click_stats_query = click_stats_query.group_by(ClickStats.offer_id)
        click_stats_result = await self.db.execute(click_stats_query)
        click_stats_map = {
            row.offer_id: row.click_count
            for row in click_stats_result.all()
        }
        
        # 批量查询转化统计
        conversion_query = (
            select(
                ClickStats.offer_id,
                func.count(PostbackConversion.id).label('conversion_count'),
                func.sum(PostbackConversion.original_payout).label('total_po')
            )
            .join(
                PostbackConversion,
                PostbackConversion.click_id == ClickStats.click_id
            )
            .where(ClickStats.offer_id.in_(offer_ids))
        )
        
        if start_datetime:
            conversion_query = conversion_query.where(
                PostbackConversion.created_at >= start_datetime
            )
        if end_datetime:
            conversion_query = conversion_query.where(
                PostbackConversion.created_at <= end_datetime
            )
        if client_publisher_ids is not None:
            conversion_query = conversion_query.where(
                ClickStats.publisher_id.in_(client_publisher_ids)
            )
        
        conversion_query = conversion_query.group_by(ClickStats.offer_id)
        conversion_result = await self.db.execute(conversion_query)
        conversion_map = {
            row.offer_id: {
                'count': row.conversion_count or 0,
                'po': float(row.total_po) if row.total_po else 0.0
            }
            for row in conversion_result.all()
        }
        
        # 构建响应数据
        stats_list = []
        for offer in offers:
            click_count = click_stats_map.get(offer.id, 0)
            conversion_data = conversion_map.get(offer.id, {'count': 0, 'po': 0.0})
            conversion_count = conversion_data['count']
            po = conversion_data['po']
            
            # 计算转化率
            cr = (conversion_count / click_count * 100) if click_count > 0 else 0.0
            
            stats_list.append({
                "offer_id": offer.id,
                "offer_name": offer.offer_name,
                "click_count": click_count,
                "conversion_count": conversion_count,
                "cr": round(cr, 2),
                "po": po
            })
        
        # 按点击数量排序
        stats_list.sort(key=lambda x: x['click_count'], reverse=True)
        
        return stats_list

