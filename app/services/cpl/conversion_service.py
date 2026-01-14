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
    User, UserRole, Client, PostbackNotification
)
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
        返回完整统计数据，包括点击、转化、转化率、支付金额等
        
        Args:
            current_user: 当前用户
            start_date: 开始日期
            end_date: 结束日期
            offer_id: Offer ID过滤
            publisher_id: 渠道ID过滤
            advertiser_id: 广告主ID过滤
        
        Returns:
            Dict: 统计信息，包含 total_clicks, total_conversions, cr, total_po, stats_list
        """
        # 解析日期
        start_datetime = None
        end_datetime = None
        
        if start_date:
            start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
        if end_date:
            # 结束日期需要包含当天的所有时间，所以+1天并使用00:00:00作为上界（不包含）
            end_datetime = parse_date_to_app_timezone(end_date, is_end_date=False) + timedelta(days=1)
        
        # 如果没有指定日期，默认查询最近30天
        if not start_datetime:
            start_datetime = get_app_now_naive() - timedelta(days=30)
            start_datetime = start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        if not end_datetime:
            end_datetime = get_app_now_naive()
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # 权限过滤：客户只能查看自己的数据
        client_publisher_ids = None
        if current_user.role == UserRole.CLIENT:
            client_result = await self.db.execute(
                select(Client.id).where(Client.user_id == current_user.id).limit(1)
            )
            client_id = client_result.scalar_one_or_none()
            if client_id:
                publisher_result = await self.db.execute(
                    select(Publisher.id).where(
                        and_(
                            Publisher.client_id == client_id,
                            Publisher.is_active == True
                        )
                    )
                )
                client_publisher_ids = list(publisher_result.scalars().all())
            else:
                # 客户没有关联的Client记录，返回空统计
                return {
                    "total_clicks": 0,
                    "total_conversions": 0,
                    "cr": 0,
                    "total_po": 0.0,
                    "stats_list": [],
                    "start_date": start_date or (start_datetime.strftime("%Y-%m-%d")),
                    "end_date": end_date or (end_datetime.strftime("%Y-%m-%d"))
                }
        
        # 构建点击查询条件
        click_conditions = [
            ClickStats.click_time >= start_datetime,
            ClickStats.click_time < end_datetime
        ]
        
        # 构建转化查询条件
        conversion_conditions = [
            PostbackConversion.created_at >= start_datetime,
            PostbackConversion.created_at < end_datetime
        ]
        
        # 如果是客户用户，添加渠道过滤条件
        if client_publisher_ids is not None:
            click_conditions.append(ClickStats.publisher_id.in_(client_publisher_ids))
        
        if offer_id:
            click_conditions.append(ClickStats.offer_id == offer_id)
        
        if publisher_id:
            click_conditions.append(ClickStats.publisher_id == publisher_id)
        
        if advertiser_id:
            click_conditions.append(ClickStats.advertiser_id == advertiser_id)
        
        # 统计总点击数量
        click_query = select(func.count(ClickStats.id)).where(and_(*click_conditions))
        total_clicks = (await self.db.execute(click_query)).scalar() or 0
        
        # 统计总转化数量（需要通过ClickStats关联来过滤）
        # 如果是客户用户，只统计已成功通知给渠道的转化（不超过下游Cap的真实转化）
        click_alias_for_count = aliased(ClickStats)
        conversion_query = select(func.count(PostbackConversion.id))
        
        if client_publisher_ids is not None or offer_id is not None or publisher_id is not None:
            conversion_query = conversion_query.join(
                click_alias_for_count, PostbackConversion.click_id == click_alias_for_count.click_id
            )
            # 如果是客户用户，只统计已成功通知给渠道的转化
            if current_user.role == UserRole.CLIENT:
                notification_alias_for_count = aliased(PostbackNotification)
                conversion_query = conversion_query.outerjoin(
                    notification_alias_for_count,
                    and_(
                        notification_alias_for_count.conversion_id == PostbackConversion.id,
                        notification_alias_for_count.publisher_id == click_alias_for_count.publisher_id,
                        notification_alias_for_count.notification_type == 'forward',
                        notification_alias_for_count.notification_status == 'sent'  # 只统计已成功发送的
                    )
                )
                conversion_query = conversion_query.where(
                    notification_alias_for_count.id.isnot(None)
                )
            
            count_conditions = list(conversion_conditions)
            if client_publisher_ids is not None:
                count_conditions.append(click_alias_for_count.publisher_id.in_(client_publisher_ids))
            if offer_id is not None:
                count_conditions.append(click_alias_for_count.offer_id == offer_id)
            if publisher_id is not None:
                count_conditions.append(click_alias_for_count.publisher_id == publisher_id)
            conversion_query = conversion_query.where(and_(*count_conditions))
        else:
            # 如果是客户用户，只统计已成功通知给渠道的转化
            if current_user.role == UserRole.CLIENT:
                notification_alias_for_count = aliased(PostbackNotification)
                conversion_query = conversion_query.outerjoin(
                    notification_alias_for_count,
                    and_(
                        notification_alias_for_count.conversion_id == PostbackConversion.id,
                        notification_alias_for_count.notification_type == 'forward',
                        notification_alias_for_count.notification_status == 'sent'  # 只统计已成功发送的
                    )
                )
                conversion_query = conversion_query.where(
                    notification_alias_for_count.id.isnot(None)
                )
            conversion_query = conversion_query.where(and_(*conversion_conditions))
        
        total_conversions = (await self.db.execute(conversion_query)).scalar() or 0
        
        # 计算总转化率
        cr = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
        
        # 统计总支付金额（PO）- 使用原始 payout
        # 如果是客户用户，只统计已成功通知给渠道的转化（不超过下游Cap的真实转化）
        click_alias_for_po = aliased(ClickStats)
        po_query = select(func.sum(PostbackConversion.original_payout))
        
        if client_publisher_ids is not None or offer_id is not None or publisher_id is not None:
            po_query = po_query.join(
                click_alias_for_po, PostbackConversion.click_id == click_alias_for_po.click_id
            )
            # 如果是客户用户，只统计已成功通知给渠道的转化
            if current_user.role == UserRole.CLIENT:
                notification_alias_for_po = aliased(PostbackNotification)
                po_query = po_query.outerjoin(
                    notification_alias_for_po,
                    and_(
                        notification_alias_for_po.conversion_id == PostbackConversion.id,
                        notification_alias_for_po.publisher_id == click_alias_for_po.publisher_id,
                        notification_alias_for_po.notification_type == 'forward',
                        notification_alias_for_po.notification_status == 'sent'  # 只统计已成功发送的
                    )
                )
                po_query = po_query.where(
                    notification_alias_for_po.id.isnot(None)
                )
            
            po_conditions = list(conversion_conditions)
            if client_publisher_ids is not None:
                po_conditions.append(click_alias_for_po.publisher_id.in_(client_publisher_ids))
            if offer_id is not None:
                po_conditions.append(click_alias_for_po.offer_id == offer_id)
            if publisher_id is not None:
                po_conditions.append(click_alias_for_po.publisher_id == publisher_id)
            po_query = po_query.where(and_(*po_conditions))
        else:
            # 如果是客户用户，只统计已成功通知给渠道的转化
            if current_user.role == UserRole.CLIENT:
                notification_alias_for_po = aliased(PostbackNotification)
                po_query = po_query.outerjoin(
                    notification_alias_for_po,
                    and_(
                        notification_alias_for_po.conversion_id == PostbackConversion.id,
                        notification_alias_for_po.notification_type == 'forward',
                        notification_alias_for_po.notification_status == 'sent'  # 只统计已成功发送的
                    )
                )
                po_query = po_query.where(
                    notification_alias_for_po.id.isnot(None)
                )
            po_query = po_query.where(and_(*conversion_conditions))
        
        total_po = float((await self.db.execute(po_query)).scalar() or 0)
        
        # 按Offer和Publisher分组统计点击
        click_group_query = select(
            ClickStats.offer_id,
            ClickStats.publisher_id,
            func.count(ClickStats.id).label('click_count')
        ).where(and_(*click_conditions)).group_by(ClickStats.offer_id, ClickStats.publisher_id)
        
        click_group_result = await self.db.execute(click_group_query)
        click_groups = click_group_result.all()
        
        # 构建统计字典
        stats_dict = {}
        offer_ids = set()
        publisher_ids = set()
        
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
            
            if offer_id_val:
                offer_ids.add(offer_id_val)
            if publisher_id_val:
                publisher_ids.add(publisher_id_val)
        
        # 获取所有转化记录，按offer_id和关联的publisher_id分组
        # 如果是客户用户，只统计已成功通知给渠道的转化（不超过下游Cap的真实转化）
        click_alias = aliased(ClickStats)
        conversion_group_query = select(
            click_alias.offer_id.label("offer_id"),
            click_alias.publisher_id,
            func.count(PostbackConversion.id).label('conversion_count'),
            func.sum(PostbackConversion.original_payout).label('total_po')
        ).outerjoin(
            click_alias, PostbackConversion.click_id == click_alias.click_id
        )
        
        # 如果是客户用户，只统计已成功通知给渠道的转化
        if current_user.role == UserRole.CLIENT:
            notification_alias = aliased(PostbackNotification)
            conversion_group_query = conversion_group_query.outerjoin(
                notification_alias,
                and_(
                    notification_alias.conversion_id == PostbackConversion.id,
                    notification_alias.publisher_id == click_alias.publisher_id,
                    notification_alias.notification_type == 'forward',
                    notification_alias.notification_status == 'sent'  # 只统计已成功发送的
                )
            )
            # 添加条件：只统计有成功通知记录的转化
            conversion_group_query = conversion_group_query.where(
                notification_alias.id.isnot(None)
            )
        
        # 构建转化查询条件
        conversion_group_conditions = list(conversion_conditions)
        if offer_id is not None:
            conversion_group_conditions.append(click_alias.offer_id == offer_id)
        if publisher_id:
            conversion_group_conditions.append(click_alias.publisher_id == publisher_id)
        if client_publisher_ids is not None:
            conversion_group_conditions.append(click_alias.publisher_id.in_(client_publisher_ids))
        
        conversion_group_query = conversion_group_query.where(and_(*conversion_group_conditions))
        conversion_group_query = conversion_group_query.group_by(
            click_alias.offer_id,
            click_alias.publisher_id
        )
        
        conversion_group_result = await self.db.execute(conversion_group_query)
        conversion_groups = conversion_group_result.all()
        
        # 处理转化数据
        for offer_id_val, pub_id_val, conv_count_val, total_po_val in conversion_groups:
            safe_offer_id = offer_id_val if offer_id_val is not None else 0
            safe_pub_id = pub_id_val if pub_id_val is not None else 0
            
            key = (safe_offer_id, safe_pub_id)
            if key not in stats_dict:
                stats_dict[key] = {
                    "offer_id": safe_offer_id,
                    "publisher_id": safe_pub_id,
                    "click_count": 0,
                    "conversion_count": 0,
                    "po": 0.0,
                    "po_after_discount": 0.0
                }
            
            stats_dict[key]["conversion_count"] += conv_count_val
            stats_dict[key]["po"] += float(total_po_val) if total_po_val else 0.0
            
            if safe_offer_id:
                offer_ids.add(safe_offer_id)
            if safe_pub_id:
                publisher_ids.add(safe_pub_id)
        
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
        
        # 计算PO（扣价后）和构建响应数据
        stats_list = []
        for key, stat in stats_dict.items():
            offer_id_val, publisher_id_val = key
            
            # 获取关联信息
            offer = offers_map.get(offer_id_val) if offer_id_val else None
            advertiser = advertisers_map.get(offer_id_val) if offer_id_val else None
            publisher = publishers_map.get(publisher_id_val) if publisher_id_val else None
            
            offer_name = offer.offer_name if offer else ("未关联Offer" if offer_id_val else "未关联Offer")
            advertiser_name = advertiser.advertiser_name if advertiser else None
            publisher_name = publisher.publisher_name if publisher else ("未关联渠道" if publisher_id_val else "未关联渠道")
            
            # 计算PO（扣价后）- 需要查询该组合下的所有转化记录
            po_after_discount = 0.0
            if publisher_id_val and offer_id_val:
                conversions_query = select(PostbackConversion).join(
                    click_alias, PostbackConversion.click_id == click_alias.click_id
                ).where(
                    and_(
                        click_alias.offer_id == offer_id_val,
                        click_alias.publisher_id == publisher_id_val,
                        *conversion_conditions
                    )
                )
                conversions_result = await self.db.execute(conversions_query)
                conversions = conversions_result.scalars().all()
                
                for conversion in conversions:
                    # 使用扣后的 payout
                    if conversion.payout:
                        po_after_discount += conversion.payout
            else:
                po_after_discount = stat["po"]
            
            # 计算CR
            cr_val = (stat["conversion_count"] / stat["click_count"] * 100) if stat["click_count"] > 0 else 0
            
            # 计算收益：收益 = conversion_count * PO(扣减后的)
            # po_after_discount 已经是所有转化的总PO扣减后，所以收益 = po_after_discount
            revenue = round(po_after_discount, 2) if stat["conversion_count"] > 0 else 0.0
            
            stats_list.append({
                "offer_id": offer_id_val,
                "offer_name": offer_name,
                "advertiser_id": offer.advertiser_id if offer else None,
                "advertiser_name": advertiser_name,
                "publisher_id": publisher_id_val,
                "publisher_name": publisher_name,
                "click_count": stat["click_count"],
                "conversion_count": stat["conversion_count"],
                "cr": round(cr_val, 2),
                "po": stat["po"],
                "po_after_discount": round(po_after_discount, 2),
                "revenue": revenue
            })
        
        # 按点击数量排序
        stats_list.sort(key=lambda x: x['click_count'], reverse=True)
        
        return {
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "cr": round(cr, 2),
            "total_po": total_po,
            "stats_list": stats_list,
            "start_date": start_date or (start_datetime.strftime("%Y-%m-%d")),
            "end_date": end_date or (end_datetime.strftime("%Y-%m-%d"))
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
                client_publisher_ids = list(publisher_result.scalars().all())
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
        # 如果是客户用户，只统计已成功通知给渠道的转化（不超过下游Cap的真实转化）
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
        
        # 如果是客户用户，只统计已成功通知给渠道的转化
        if current_user.role == UserRole.CLIENT:
            notification_alias_for_list = aliased(PostbackNotification)
            conversion_query = conversion_query.outerjoin(
                notification_alias_for_list,
                and_(
                    notification_alias_for_list.conversion_id == PostbackConversion.id,
                    notification_alias_for_list.publisher_id == ClickStats.publisher_id,
                    notification_alias_for_list.notification_type == 'forward',
                    notification_alias_for_list.notification_status == 'sent'  # 只统计已成功发送的
                )
            )
            conversion_query = conversion_query.where(
                notification_alias_for_list.id.isnot(None)
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

