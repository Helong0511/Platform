"""
转化统计业务服务层。

职责：
- 转化总览（get_conversion_summary）：按 Offer×渠道 聚合点击、转化、CR、PO 与利润
- 按 Offer 维度汇总（get_conversions_by_offer）
- 客户角色数据隔离：仅统计所属 Client 下激活渠道的点击与转化
- 客户侧 downstream_cap 上限裁剪，触顶时可自动关闭关联短链接

统计口径：全局汇总优先 click_id 关联 Click，且仅计入激活且 status=Active 的 Offer；
分组统计规则略有差异，详见各方法内分段注释。

对应路由：app/api_v1/cpl/conversions
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, case, cast, Integer
from sqlalchemy.orm import aliased

from app.models.models import (
    PostbackConversion, Click, Offer, Publisher, Advertiser,
    User, UserRole, Client, PostbackNotification, OfferPublisherAssignment
)
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.utils import parse_date_to_app_timezone, get_app_now_naive
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 客户不可见的上游金额与广告主字段（文档约定仅管理员可见）
_CLIENT_HIDDEN_SUMMARY_TOTAL_KEYS = frozenset({"total_po", "total_profit"})
_CLIENT_HIDDEN_STATS_KEYS = frozenset({
    "po",
    "adv_po",
    "advertiser_id",
    "advertiser_name",
})


def _sanitize_conversion_summary_for_client(summary: Dict[str, Any]) -> Dict[str, Any]:
    """剥离转化总览中客户不应看到的上游 PO / 利润 / 广告主信息。"""
    sanitized = {
        key: value
        for key, value in summary.items()
        if key not in _CLIENT_HIDDEN_SUMMARY_TOTAL_KEYS
    }
    stats_list = sanitized.get("stats_list") or []
    sanitized["stats_list"] = [
        {
            key: value
            for key, value in item.items()
            if key not in _CLIENT_HIDDEN_STATS_KEYS
        }
        for item in stats_list
    ]
    return sanitized


def _sanitize_by_offer_stats_for_client(
    stats_list: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """按 Offer 汇总时剥离上游 PO 字段。"""
    return [
        {key: value for key, value in item.items() if key != "po"}
        for item in stats_list
    ]


class ConversionService:
    """
    转化统计服务（无 BaseService 继承）。

    面向管理端报表与客户仪表盘，聚合 Click 与 PostbackConversion 数据，
    并叠加扣量、下游 PO 上限等业务规则计算可见收益。
    """

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 异步 SQLAlchemy 会话
        """
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
        获取转化总览统计（仪表盘核心接口）。

        默认查询最近 30 天；客户用户无渠道时返回全零结构。
        返回全局汇总与按 (offer_id, publisher_id) 分组的 stats_list。

        Args:
            current_user: 当前登录用户，CLIENT 角色触发数据隔离
            start_date: 起始日期 YYYY-MM-DD，可选
            end_date: 结束日期 YYYY-MM-DD，可选（含当日）
            offer_id: 按 Offer 过滤
            publisher_id: 按渠道过滤
            advertiser_id: 按广告主过滤

        Returns:
            Dict: total_clicks、total_conversions、cr、total_po、
                total_po_after_discount、total_profit、conversion_cap、
                stats_list、start_date、end_date
        """
        # --- 日期范围：默认近 30 天，结束日含全天 ---
        start_datetime = None
        end_datetime = None

        if start_date:  # 开始日期
            # 将开始日期解析为应用时区的datetime对象
            start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
        if end_date:  # 结束日期
            # 结束日期需要包含当天的所有时间，所以+1天并使用00:00:00作为上界（不包含）
            end_datetime = parse_date_to_app_timezone(end_date, is_end_date=False) + timedelta(days=1)

        # 如果没有指定日期，默认查询最近30天
        if not start_datetime:  # 开始日期默认30天前
            start_datetime = get_app_now_naive() - timedelta(days=30)
            start_datetime = start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        if not end_datetime:  # 结束日期默认当前时间
            end_datetime = get_app_now_naive()
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)

        # --- 客户角色：解析 client_id 与可见渠道列表 ---
        client_publisher_ids = None
        client_id = None
        if current_user.role == UserRole.CLIENT:
            # 查询客户关联的Client记录
            client_result = await self.db.execute(
                select(Client.id).where(Client.user_id == current_user.id).limit(1)
            )
            client_id = client_result.scalar_one_or_none()
            if client_id:
                # 查询客户关联的所有活跃渠道
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
                        "total_po_after_discount": 0.0,
                        "total_profit": 0.0,
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
                    "total_po_after_discount": 0.0,
                    "total_profit": 0.0,
                    "stats_list": [],
                    "start_date": start_date or (start_datetime.strftime("%Y-%m-%d")),
                    "end_date": end_date or (end_datetime.strftime("%Y-%m-%d"))
                }

        # --- 构建点击/转化公共时间窗与维度条件 ---
        click_conditions = [
            Click.click_time >= start_datetime,
            Click.click_time < end_datetime
        ]

        # 构建转化查询条件
        conversion_conditions = [
            PostbackConversion.created_at >= start_datetime,
            PostbackConversion.created_at < end_datetime,
            # 包含所有状态的转化，包括CapReached
            # PostbackConversion.conversion_status == 'Approved'
        ]

        # 如果是客户用户，添加渠道过滤条件
        if client_publisher_ids is not None:
            click_conditions.append(Click.publisher_id.in_(client_publisher_ids))

        if offer_id:
            click_conditions.append(Click.offer_id == offer_id)

        if publisher_id:
            click_conditions.append(Click.publisher_id == publisher_id)

        if advertiser_id:
            click_conditions.append(Click.advertiser_id == advertiser_id)

        # 统计总点击数量（也可由下方分组 sum，保留一次 COUNT 以兼容无分组维度的空结果）
        click_query = select(func.count(Click.id)).where(and_(*click_conditions))
        total_clicks = (await self.db.execute(click_query)).scalar() or 0

        # 全局转化 COUNT/SUM 已删除：结果会被分组汇总覆盖，重复扫大表无收益。
        # totals 仅从下方 GROUP BY 路径汇总，保证与明细一致。
        total_conversions = 0
        total_po = 0.0
        total_po_after_discount = 0.0

        # --- 分组统计：先聚合点击，再合并转化 ---
        click_group_query = select(
            Click.offer_id,
            Click.publisher_id,
            func.count(Click.id).label('click_count')
        ).where(and_(*click_conditions)).group_by(Click.offer_id, Click.publisher_id)

        click_group_result = await self.db.execute(click_group_query)
        click_groups = click_group_result.all()

        # 构建统计字典
        stats_dict = {}
        offer_ids = set()
        publisher_ids = set()

        # 处理点击数据
        for offer_id_val, publisher_id_val, click_count_val in click_groups:
            # 只处理有offer_id的记录，publisher_id可以为None
            if not offer_id_val:
                continue

            # 为publisher_id为None的记录使用0作为分组键
            safe_publisher_id = publisher_id_val if publisher_id_val is not None else 0
            key = (offer_id_val, safe_publisher_id)
            stats_dict[key] = {
                "offer_id": offer_id_val,
                "publisher_id": safe_publisher_id,
                "click_count": click_count_val,
                "conversion_count": 0,
                "po": 0.0,
                "po_after_discount": 0.0
            }

            if offer_id_val:
                offer_ids.add(offer_id_val)
            if safe_publisher_id:
                publisher_ids.add(safe_publisher_id)

        # 获取所有转化记录，按offer_id和关联的publisher_id分组
        # 客户用户：支持通过Click.publisher_id过滤
        # 注意：使用 join 确保只统计有 Click 关联的转化（用于分组）
        # 注意：只统计 Offer 激活的转化（不计入未激活 Offer 的转化）
        click_alias = aliased(Click)
        offer_alias = aliased(Offer)

        # 构建分组查询条件
        conversion_group_conditions = list(conversion_conditions)
        # 不强制要求click_id不为空，允许统计没有click_id的转化记录
        # conversion_group_conditions.append(PostbackConversion.click_id.isnot(None))
        # 使用左连接，允许没有click_id的转化记录
        # conversion_group_conditions.append(PostbackConversion.click_id == click_alias.click_id)
        # conversion_group_conditions.append(click_alias.offer_id == offer_alias.id)
        # 不强制要求Offer为激活状态，允许统计所有状态的Offer
        # conversion_group_conditions.append(offer_alias.is_active == True)
        # conversion_group_conditions.append(offer_alias.status == 'Active')
        # 包含所有状态的转化，包括CapReached
        # conversion_group_conditions.append(PostbackConversion.conversion_status == 'Approved')

        # 只有当click_alias不为NULL时才添加这些条件
        if offer_id is not None:
            conversion_group_conditions.append(
                click_alias.offer_id == offer_id
            )
        if publisher_id:
            conversion_group_conditions.append(
                click_alias.publisher_id == publisher_id
            )
        if client_publisher_ids is not None:
            conversion_group_conditions.append(
                click_alias.publisher_id.in_(client_publisher_ids)
            )
        if advertiser_id is not None:
            conversion_group_conditions.append(
                click_alias.advertiser_id == advertiser_id
            )

        # 构建分组查询：使用内连接，只统计有Click记录的转化
        # 确保只统计有Click记录且publisher_id在客户关联渠道列表中的转化
        conversion_group_query = select(
            click_alias.offer_id.label("offer_id"),
            click_alias.publisher_id.label("publisher_id"),
            func.count(PostbackConversion.id).label('conversion_count'),
            func.sum(PostbackConversion.original_payout).label('total_po_original'),
            func.sum(PostbackConversion.payout).label('total_po_discounted')
        ).join(
            click_alias, PostbackConversion.click_id == click_alias.click_id
        ).join(
            offer_alias, click_alias.offer_id == offer_alias.id
        ).where(
            and_(
                *conversion_group_conditions,
                click_alias.offer_id.isnot(None),
                click_alias.publisher_id.isnot(None)
            )
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
        # 第一遍：收集所有转化数据，计算总转化数量和总支付金额，收集offer_ids和publisher_ids
        calculated_total_conversions = 0
        calculated_total_po = 0.0
        calculated_total_po_after_discount = 0.0
        conversion_data_list = []  # 暂存转化数据，用于第二遍处理

        for offer_id_val, pub_id_val, conv_count_val, total_po_original_val, total_po_discounted_val in conversion_groups:
            # 由于使用内连接，offer_id和publisher_id不会为None
            key = (offer_id_val, pub_id_val)
            # 如果统计字典中不存在该键，初始化一个新的统计项
            if key not in stats_dict:
                stats_dict[key] = {
                    "offer_id": offer_id_val,
                    "publisher_id": pub_id_val,
                    "click_count": 0,
                    "conversion_count": 0,
                    "po": 0.0,
                    "po_after_discount": 0.0
                }

            # 更新转化数量
            stats_dict[key]["conversion_count"] += conv_count_val
            # po 字段使用原始金额（管理员可见）
            po_original_val = float(total_po_original_val) if total_po_original_val else 0.0
            stats_dict[key]["po"] += po_original_val

            # 暂存转化数据，用于第二遍处理
            po_discounted_val = float(total_po_discounted_val) if total_po_discounted_val else 0.0
            conversion_data_list.append({
                "key": key,
                "conv_count_val": conv_count_val,
                "po_original_val": po_original_val,
                "po_discounted_val": po_discounted_val,
                "safe_offer_id": offer_id_val,
                "safe_pub_id": pub_id_val
            })

            # 累加转化数量和支付金额（从分组统计结果汇总，确保与分组统计一致）
            calculated_total_conversions += conv_count_val
            calculated_total_po += po_original_val
            calculated_total_po_after_discount += po_discounted_val

            # 更新offer_ids和publisher_ids集合
            offer_ids.add(offer_id_val)
            publisher_ids.add(pub_id_val)

        # 使用从分组统计汇总的总转化数量和总支付金额（确保与分组统计一致）
        # 总转化数量应该等于所有分组转化数量的总和
        total_conversions = calculated_total_conversions
        # 总支付金额：使用原始金额（管理员可见）
        total_po = calculated_total_po
        # 扣价后的总支付金额（所有用户可见）
        total_po_after_discount = calculated_total_po_after_discount
        # 计算总利润：总支付金额 - 扣价后的总支付金额
        total_profit = total_po - total_po_after_discount

        # 重新计算总转化率（使用更新后的总转化数量）
        cr = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0

        # --- 批量加载维度名称与 Offer-渠道分配（避免 N+1）---
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

        # 批量加载OfferPublisherAssignment信息（用于获取Pub PO）
        offer_publisher_assignments_map = {}
        if offer_ids and publisher_ids:
            # 使用 in_ 条件批量查询所有相关的分配记录
            assignments_result = await self.db.execute(
                select(OfferPublisherAssignment).where(
                    and_(
                        OfferPublisherAssignment.offer_id.in_(offer_ids),
                        OfferPublisherAssignment.publisher_id.in_(publisher_ids)
                    )
                )
            )
            for assignment in assignments_result.scalars().all():
                key = (assignment.offer_id, assignment.publisher_id)
                offer_publisher_assignments_map[key] = assignment

        # --- 第二遍：按 affiliate_payout 裁剪下游可见收益 ---
        calculated_total_po_after_discount = 0.0
        for conv_data in conversion_data_list:
            key = conv_data["key"]
            conv_count_val = conv_data["conv_count_val"]
            po_original_val = conv_data["po_original_val"]
            po_discounted_val = conv_data["po_discounted_val"]
            safe_offer_id = conv_data["safe_offer_id"]
            safe_pub_id = conv_data["safe_pub_id"]

            # 计算考虑下游PO限制后的实际收益（与Postback管理的PayOut(扣)逻辑一致）
            assignment_key = (safe_offer_id, safe_pub_id)
            actual_revenue = po_discounted_val  # 默认使用扣量后的金额

            if assignment_key in offer_publisher_assignments_map:
                assignment = offer_publisher_assignments_map[assignment_key]
                if assignment and assignment.affiliate_payout is not None:
                    # 上游金额（使用original_payout）
                    upstream_amount = po_original_val
                    # 如果上游金额大于下游PO，使用下游PO金额
                    if upstream_amount > assignment.affiliate_payout:
                        # 实际收益应该是 min(上游金额, 下游PO)
                        # 由于我们统计的是总金额，需要按比例计算
                        # 简化处理：使用扣量后的金额，但不超过下游PO * 转化数量
                        actual_revenue = min(po_discounted_val, assignment.affiliate_payout * conv_count_val)

            stats_dict[key]["po_after_discount"] += actual_revenue
            calculated_total_po_after_discount += actual_revenue

        # 更新扣价后的总支付金额和总利润
        total_po_after_discount = calculated_total_po_after_discount
        total_profit = total_po - total_po_after_discount

        # --- 客户角色：downstream_cap 仅裁剪展示（只读，不关短链）---
        # 关短链由 Postback Cap 流水线负责；GET 汇总不写库。
        conversion_cap = 0
        if current_user.role == UserRole.CLIENT and client_id:
            # 展示口径：客户全量渠道 downstream_cap 之和（与筛选结果集无关）
            client_cap_result = await self.db.execute(
                select(func.sum(OfferPublisherAssignment.downstream_cap))
                .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
                .where(
                    and_(
                        Publisher.client_id == client_id,
                        Publisher.is_active == True,
                        OfferPublisherAssignment.is_active == True,
                        OfferPublisherAssignment.downstream_cap.isnot(None)
                    )
                )
            )
            conversion_cap = int(client_cap_result.scalar() or 0)

            # 行级裁剪仍用已加载的 assignment map
            has_row_caps = any(
                a.downstream_cap is not None
                for a in offer_publisher_assignments_map.values()
            )
            
            # 对于客户用户，应用转化上限：每个(offer_id, publisher_id)组合的转化数不能超过其downstream_cap
            if has_row_caps or conversion_cap > 0:
                # 重新计算总转化数和总收益
                total_conversions = 0
                total_po_after_discount = 0.0
                
                # 对每个(offer_id, publisher_id)组合应用downstream_cap限制（仅内存裁剪）
                for key, stat in stats_dict.items():
                    offer_id_val, publisher_id_val = key
                    # 查找该(offer_id, publisher_id)组合的downstream_cap
                    assignment_key = (offer_id_val, publisher_id_val)
                    assignment = offer_publisher_assignments_map.get(assignment_key)
                    
                    if assignment and assignment.downstream_cap is not None:
                        # 应用downstream_cap限制
                        max_conversions = assignment.downstream_cap
                        if stat["conversion_count"] > max_conversions:
                            # 计算调整比例
                            adjustment_ratio = max_conversions / stat["conversion_count"]
                            # 调整转化数
                            stat["conversion_count"] = max_conversions
                            # 按相同比例调整收益
                            stat["po_after_discount"] *= adjustment_ratio
                            # 重新计算CR
                            if stat["click_count"] > 0:
                                cr_val = (stat["conversion_count"] / stat["click_count"] * 100)
                                stat["cr"] = round(cr_val, 2)
                    
                    # 累加总转化数和总收益
                    total_conversions += stat["conversion_count"]
                    total_po_after_discount += stat["po_after_discount"]
                
                # 重新计算总利润
                total_profit = total_po - total_po_after_discount
                # 重新计算转化率
                cr = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0

        # 计算PO（扣价后）和构建响应数据
        stats_list = []
        for key, stat in stats_dict.items():
            offer_id_val, publisher_id_val = key

            # 获取关联信息
            offer = offers_map.get(offer_id_val) if offer_id_val else None
            advertiser = advertisers_map.get(offer_id_val) if offer_id_val else None
            publisher = publishers_map.get(publisher_id_val) if publisher_id_val else None

            # 获取offer名称、广告主名称和渠道名称
            offer_name = offer.offer_name if offer else ("未关联Offer" if offer_id_val else "未关联Offer")
            advertiser_name = advertiser.advertiser_name if advertiser else None
            publisher_name = publisher.publisher_name if publisher else (
                "未关联渠道" if publisher_id_val else "未关联渠道")

            # po_after_discount 已经在分组统计时计算好了（使用扣减后的金额）
            po_after_discount = stat["po_after_discount"]

            # 计算CR（转化率）
            cr_val = (stat["conversion_count"] / stat["click_count"] * 100) if stat["click_count"] > 0 else 0

            # 计算收益：收益 = conversion_count * PO(扣减后的)
            # po_after_discount 已经是所有转化的总PO扣减后，所以收益 = po_after_discount
            revenue = round(po_after_discount, 2) if stat["conversion_count"] > 0 else 0.0

            # 获取Adv PO（上游给的单价，即Offer.payout）
            adv_po = float(offer.payout) if offer and offer.payout is not None else None

            # 获取Pub PO（给下游的单价，优先从OfferPublisherAssignment获取，如果没有则使用Offer.affiliate_payout）
            pub_po = None
            assignment_key = (offer_id_val, publisher_id_val)
            assignment = offer_publisher_assignments_map.get(assignment_key)
            if assignment and assignment.affiliate_payout is not None:
                pub_po = float(assignment.affiliate_payout)
            elif offer and offer.affiliate_payout is not None:
                pub_po = float(offer.affiliate_payout)

            # 获取GEO（国家，从Offer.country获取）
            geo = offer.country if offer and offer.country else None

            # 构建统计项并添加到列表
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
                "revenue": revenue,
                "adv_po": adv_po,
                "pub_po": pub_po,
                "geo": geo
            })

        # 按点击数量排序
        stats_list.sort(key=lambda x: x['click_count'], reverse=True)

        # 返回最终的统计结果
        summary = {
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "cr": round(cr, 2),
            "total_po": round(total_po, 2),
            "total_po_after_discount": round(total_po_after_discount, 2),
            "total_profit": round(total_profit, 2),
            "conversion_cap": conversion_cap,
            "stats_list": stats_list,
            "start_date": start_date or (start_datetime.strftime("%Y-%m-%d")),
            "end_date": end_date or (end_datetime.strftime("%Y-%m-%d"))
        }
        if current_user.role == UserRole.CLIENT:
            return _sanitize_conversion_summary_for_client(summary)
        return summary

    async def get_conversions_by_offer(
            self,
            current_user: User,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        按 Offer 维度汇总点击、转化、CR 与 PO。

        仅统计时间窗内有过转化记录的 Offer（含未激活 Offer）；
        转化计数仍限定 Active 且 is_active 的 Offer。

        Args:
            current_user: 当前登录用户，CLIENT 角色限定所属渠道
            start_date: 起始日期，可选
            end_date: 结束日期，可选

        Returns:
            List[Dict]: 每项含 offer_id、offer_name、click_count、
                conversion_count、cr、po，按点击量降序
        """
        # --- 日期解析 ---
        start_datetime = None
        end_datetime = None

        if start_date:
            start_datetime = parse_date_to_app_timezone(start_date)
        if end_date:
            # 使用次日零点作为排他上界，避免漏掉结束日最后一秒内的微秒记录。
            end_datetime = parse_date_to_app_timezone(end_date, is_end_date=False) + timedelta(days=1)

        # --- 客户角色：限定可见渠道 ---
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

        # --- 确定时间窗内有过转化的 Offer 集合 ---
        conversion_offer_query = (
            select(Click.offer_id)
            .join(
                PostbackConversion,
                PostbackConversion.click_id == Click.click_id
            )
            .where(Click.offer_id.isnot(None))
        )

        if start_datetime:
            conversion_offer_query = conversion_offer_query.where(
                PostbackConversion.created_at >= start_datetime
            )
        if end_datetime:
            conversion_offer_query = conversion_offer_query.where(
                PostbackConversion.created_at < end_datetime
            )
        if client_publisher_ids is not None:
            conversion_offer_query = conversion_offer_query.where(
                Click.publisher_id.in_(client_publisher_ids)
            )

        # 去重查询
        conversion_offer_query = conversion_offer_query.distinct()
        conversion_offer_result = await self.db.execute(conversion_offer_query)
        # 提取有效的offer_id
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

        # 提取所有offer的id
        offer_ids = [offer.id for offer in offers]

        # --- 批量聚合各 Offer 的点击与转化（转化仅计 Active Offer）---
        click_query = select(
            Click.offer_id,
            func.count(Click.click_id).label('click_count')
        ).where(Click.offer_id.in_(offer_ids))

        if start_datetime:
            click_query = click_query.where(
                Click.click_time >= start_datetime
            )
        if end_datetime:
            click_query = click_query.where(
                Click.click_time < end_datetime
            )
        if client_publisher_ids is not None:
            click_query = click_query.where(
                Click.publisher_id.in_(client_publisher_ids)
            )

        # 按offer_id分组
        click_query = click_query.group_by(Click.offer_id)
        click_result = await self.db.execute(click_query)
        # 构建点击统计映射
        click_map = {
            row.offer_id: row.click_count
            for row in click_result.all()
        }

        # 批量查询转化统计
        # 客户用户：直接通过Click.publisher_id过滤，显示所有属于客户的转化
        # 注意：只统计 Offer 激活的转化（不计入未激活 Offer 的转化）
        offer_alias_for_list = aliased(Offer)
        conversion_query = (
            select(
                Click.offer_id,
                func.count(PostbackConversion.id).label('conversion_count'),
                func.sum(PostbackConversion.payout).label('total_po')
            )
            .join(
                PostbackConversion,
                PostbackConversion.click_id == Click.click_id
            )
            .join(
                offer_alias_for_list,
                Click.offer_id == offer_alias_for_list.id
            )
            .where(
                and_(
                    Click.offer_id.in_(offer_ids),
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
                PostbackConversion.created_at < end_datetime
            )
        if client_publisher_ids is not None:
            conversion_query = conversion_query.where(
                Click.publisher_id.in_(client_publisher_ids)
            )

        # 按offer_id分组
        conversion_query = conversion_query.group_by(Click.offer_id)
        conversion_result = await self.db.execute(conversion_query)
        # 构建转化统计映射
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
            # 获取点击数量
            click_count = click_map.get(offer.id, 0)
            # 获取转化数据
            conversion_data = conversion_map.get(offer.id, {'count': 0, 'po': 0.0})
            conversion_count = conversion_data['count']
            po = conversion_data['po']

            # 计算转化率
            cr = (conversion_count / click_count * 100) if click_count > 0 else 0.0

            # 构建统计项
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

        if current_user.role == UserRole.CLIENT:
            return _sanitize_by_offer_stats_for_client(stats_list)
        return stats_list
