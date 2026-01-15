"""
转化服务层
封装转化相关的业务逻辑和统计查询
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, case, cast, Integer
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
        client_id = None
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
                # 如果客户没有关联的渠道，返回空统计
                if not client_publisher_ids:
                    return {
                        "total_clicks": 0,
                        "total_conversions": 0,
                        "cr": 0,
                        "total_po": 0.0,
                        "stats_list": [],
                        "start_date": start_date or (start_datetime.strftime("%Y-%m-%d")),
                        "end_date": end_date or (end_datetime.strftime("%Y-%m-%d"))
                    }
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
        
        # 统计总转化数量（支持多种关联方式：click_id、gid、client_id）
        # 客户用户：支持通过ClickStats.publisher_id、gid字段、client_id字段过滤
        # 注意：只统计 Offer 激活的转化（不计入未激活 Offer 的转化）
        click_alias_for_count = aliased(ClickStats)
        offer_alias_for_count = aliased(Offer)
        
        # 方式1：通过 click_id 关联 ClickStats（主要方式）
        count_conditions_1 = list(conversion_conditions)
        count_conditions_1.append(PostbackConversion.click_id.isnot(None))
        count_conditions_1.append(PostbackConversion.click_id == click_alias_for_count.click_id)
        count_conditions_1.append(click_alias_for_count.offer_id == offer_alias_for_count.id)
        count_conditions_1.append(offer_alias_for_count.is_active == True)
        count_conditions_1.append(offer_alias_for_count.status == 'Active')
        
        if client_publisher_ids is not None:
            count_conditions_1.append(click_alias_for_count.publisher_id.in_(client_publisher_ids))
        if offer_id is not None:
            count_conditions_1.append(click_alias_for_count.offer_id == offer_id)
        if publisher_id is not None:
            count_conditions_1.append(click_alias_for_count.publisher_id == publisher_id)
        if advertiser_id is not None:
            count_conditions_1.append(click_alias_for_count.advertiser_id == advertiser_id)
        
        conversion_query_1 = select(func.count(PostbackConversion.id)).join(
            click_alias_for_count, PostbackConversion.click_id == click_alias_for_count.click_id
        ).join(
            offer_alias_for_count, click_alias_for_count.offer_id == offer_alias_for_count.id
        ).where(and_(*count_conditions_1))
        
        count_1 = (await self.db.execute(conversion_query_1)).scalar() or 0
        
        # 方式2：通过 gid 字段匹配 publisher_id（备用方式，仅客户登录时使用）
        # 统计 click_id 存在但无法关联到 ClickStats，但 gid 匹配的记录
        # 注意：这些记录无法获取 offer_id，所以不统计（保持与主要方式一致，只统计有 offer_id 的记录）
        # 如果需要统计这些记录，需要在后续版本中扩展支持
        
        # 方式3：通过 client_id 直接匹配（备用方式，仅客户登录时使用）
        # 注意：同样，如果 click_id 为空或无法关联，无法获取 offer_id，所以不统计这些记录
        
        # 合并统计结果（当前主要使用方式1，确保所有统计的转化都有有效的 click_id 和 offer_id）
        # 注意：total_conversions 将在分组统计后从分组结果汇总计算，确保与分组统计一致
        # 这里先计算一个初始值，后续会被更新
        total_conversions = count_1
        
        # 统计总支付金额（PO）- 使用原始 payout（支持多种关联方式）
        # 客户用户：支持通过ClickStats.publisher_id、gid字段、client_id字段过滤
        # 注意：只统计 Offer 激活的转化（不计入未激活 Offer 的转化）
        click_alias_for_po = aliased(ClickStats)
        offer_alias_for_po = aliased(Offer)
        
        # 方式1：通过 click_id 关联 ClickStats（主要方式）
        po_conditions_1 = list(conversion_conditions)
        po_conditions_1.append(PostbackConversion.click_id.isnot(None))
        po_conditions_1.append(PostbackConversion.click_id == click_alias_for_po.click_id)
        po_conditions_1.append(click_alias_for_po.offer_id == offer_alias_for_po.id)
        po_conditions_1.append(offer_alias_for_po.is_active == True)
        po_conditions_1.append(offer_alias_for_po.status == 'Active')
        
        if client_publisher_ids is not None:
            po_conditions_1.append(click_alias_for_po.publisher_id.in_(client_publisher_ids))
        if offer_id is not None:
            po_conditions_1.append(click_alias_for_po.offer_id == offer_id)
        if publisher_id is not None:
            po_conditions_1.append(click_alias_for_po.publisher_id == publisher_id)
        if advertiser_id is not None:
            po_conditions_1.append(click_alias_for_po.advertiser_id == advertiser_id)
        
        po_query_1 = select(func.sum(PostbackConversion.original_payout)).join(
            click_alias_for_po, PostbackConversion.click_id == click_alias_for_po.click_id
        ).join(
            offer_alias_for_po, click_alias_for_po.offer_id == offer_alias_for_po.id
        ).where(and_(*po_conditions_1))
        
        po_1 = float((await self.db.execute(po_query_1)).scalar() or 0)
        
        # 方式2和方式3：通过 gid 或 client_id（备用方式，当前暂不统计，因为无法获取 offer_id）
        # 注意：如果 click_id 为空或无法关联，无法获取 offer_id，所以不统计这些记录
        # 在后续版本中可以扩展支持
        
        # 合并统计结果（当前主要使用方式1，确保所有统计的转化都有有效的 click_id 和 offer_id）
        total_po = po_1
        
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
        # 客户用户：支持通过ClickStats.publisher_id过滤
        # 注意：使用 join 确保只统计有 ClickStats 关联的转化（用于分组）
        # 注意：只统计 Offer 激活的转化（不计入未激活 Offer 的转化）
        click_alias = aliased(ClickStats)
        offer_alias = aliased(Offer)
        
        # 构建分组查询条件
        conversion_group_conditions = list(conversion_conditions)
        conversion_group_conditions.append(PostbackConversion.click_id.isnot(None))
        conversion_group_conditions.append(PostbackConversion.click_id == click_alias.click_id)
        conversion_group_conditions.append(click_alias.offer_id == offer_alias.id)
        conversion_group_conditions.append(offer_alias.is_active == True)
        conversion_group_conditions.append(offer_alias.status == 'Active')
        
        if offer_id is not None:
            conversion_group_conditions.append(click_alias.offer_id == offer_id)
        if publisher_id:
            conversion_group_conditions.append(click_alias.publisher_id == publisher_id)
        if client_publisher_ids is not None:
            conversion_group_conditions.append(click_alias.publisher_id.in_(client_publisher_ids))
        if advertiser_id is not None:
            conversion_group_conditions.append(click_alias.advertiser_id == advertiser_id)
        
        # 构建分组查询：使用 join 确保只统计有 click_id 关联的记录（用于分组）
        conversion_group_query = select(
            click_alias.offer_id.label("offer_id"),
            click_alias.publisher_id,
            func.count(PostbackConversion.id).label('conversion_count'),
            func.sum(PostbackConversion.original_payout).label('total_po')
        ).join(
            click_alias, PostbackConversion.click_id == click_alias.click_id
        ).join(
            offer_alias, click_alias.offer_id == offer_alias.id
        ).where(
            and_(*conversion_group_conditions)
        ).group_by(
            click_alias.offer_id,
            click_alias.publisher_id
        )
        
        # 注意：对于通过 gid 或 client_id 匹配但没有 click_id 的记录，无法确定 offer_id 和 publisher_id
        # 所以暂时不纳入分组统计。如果需要统计这些记录，可以在后续版本中通过其他方式处理
        
        conversion_group_result = await self.db.execute(conversion_group_query)
        conversion_groups = conversion_group_result.all()
        
        # 调试日志：记录查询结果
        if current_user.role == UserRole.CLIENT:
            logger.debug(
                f"客户转化统计查询: client_publisher_ids={client_publisher_ids}, "
                f"conversion_groups_count={len(conversion_groups)}, "
                f"start_date={start_date}, end_date={end_date}"
            )
        
        # 处理转化数据
        # 同时计算总转化数量和总支付金额（从分组统计结果汇总，确保与分组统计一致）
        calculated_total_conversions = 0
        calculated_total_po = 0.0
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
            po_val = float(total_po_val) if total_po_val else 0.0
            stats_dict[key]["po"] += po_val
            # 累加转化数量和支付金额
            calculated_total_conversions += conv_count_val
            calculated_total_po += po_val
            
            if safe_offer_id:
                offer_ids.add(safe_offer_id)
            if safe_pub_id:
                publisher_ids.add(safe_pub_id)
        
        # 使用从分组统计汇总的总转化数量和总支付金额（确保与分组统计一致）
        # 总转化数量应该等于所有分组转化数量的总和
        total_conversions = calculated_total_conversions
        # 总支付金额也应该等于所有分组支付金额的总和
        total_po = calculated_total_po
        
        # 重新计算总转化率（使用更新后的总转化数量）
        cr = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
        
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
            # 注意：只统计 Offer 激活的转化（不计入未激活 Offer 的转化）
            po_after_discount = 0.0
            if publisher_id_val and offer_id_val:
                offer_alias_for_discount = aliased(Offer)
                conversions_query = select(PostbackConversion).join(
                    click_alias, PostbackConversion.click_id == click_alias.click_id
                ).join(
                    offer_alias_for_discount, click_alias.offer_id == offer_alias_for_discount.id
                ).where(
                    and_(
                        click_alias.offer_id == offer_id_val,
                        click_alias.publisher_id == publisher_id_val,
                        offer_alias_for_discount.is_active == True,
                        offer_alias_for_discount.status == 'Active',
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
                if not client_publisher_ids:
                    return []
            else:
                return []
        
        # 先查询有转化数据的 Offer ID（不管 Offer 是否激活）
        # 这样确保所有有转化数据的 Offer 都会被统计
        conversion_offer_query = (
            select(ClickStats.offer_id)
            .join(
                PostbackConversion,
                PostbackConversion.click_id == ClickStats.click_id
            )
            .where(ClickStats.offer_id.isnot(None))
        )
        
        if start_datetime:
            conversion_offer_query = conversion_offer_query.where(
                PostbackConversion.created_at >= start_datetime
            )
        if end_datetime:
            conversion_offer_query = conversion_offer_query.where(
                PostbackConversion.created_at <= end_datetime
            )
        if client_publisher_ids is not None:
            conversion_offer_query = conversion_offer_query.where(
                ClickStats.publisher_id.in_(client_publisher_ids)
            )
        
        conversion_offer_query = conversion_offer_query.distinct()
        conversion_offer_result = await self.db.execute(conversion_offer_query)
        offer_ids_with_conversions = [row.offer_id for row in conversion_offer_result.all() if row.offer_id]
        
        # 如果没有转化数据，返回空列表
        if not offer_ids_with_conversions:
            return []
        
        # 获取所有有转化数据的 Offer（不管是否激活）
        offer_query = select(Offer).where(Offer.id.in_(offer_ids_with_conversions))
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
        # 客户用户：直接通过ClickStats.publisher_id过滤，显示所有属于客户的转化
        # 注意：只统计 Offer 激活的转化（不计入未激活 Offer 的转化）
        offer_alias_for_list = aliased(Offer)
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
            .join(
                offer_alias_for_list,
                ClickStats.offer_id == offer_alias_for_list.id
            )
            .where(
                and_(
                    ClickStats.offer_id.in_(offer_ids),
                    offer_alias_for_list.is_active == True,
                    offer_alias_for_list.status == 'Active'
                )
            )
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

