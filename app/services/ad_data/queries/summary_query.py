"""
广告数据 KPI 汇总查询。

功能说明：
- 对匹配记录做 SUM 聚合，计算漏斗总量与衍生指标
- 衍生指标口径与前端广告数据表格「合计行」一致（useAdDataTableFormat）
- 管理员额外返回减扣前 eCPM/收益；结果带 Redis 缓存

在系统中的位置：
- 被 ``AdDataService.get_ad_data_summary`` 与 Telegram 统计菜单调用
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.infrastructure.cache_compat import (
    generate_cache_key,
    legacy_get_cached as get_cached,
    legacy_set_cached as set_cached,
)
from app.core.query_utils import apply_date_range_filter, check_use_assignment_table
from app.core.security import is_admin
from app.models.models import AdData, Client, Product, User
from app.services.ad_data.queries.join_helpers import join_product_and_client

logger = logging.getLogger(__name__)


def compute_ad_data_derived_metrics(
    *,
    total_requests: float,
    total_matches: float,
    total_displays: float,
    total_clicks: float,
    total_revenue_after: float,
    total_revenue_before: float,
    total_pageviews: float,
    weighted_viewability: float,
    viewability_weight: float,
    for_admin: bool,
) -> Dict[str, float]:
    """
    由聚合总量计算覆盖率、eCPM、CPC 等衍生指标。

    算法与 ``frontend/src/composables/useAdDataTableFormat.js`` 合计行一致。
    """
    coverage_rate = (total_matches / total_requests * 100.0) if total_requests > 0 else 0.0
    display_rate = (total_displays / total_matches * 100.0) if total_matches > 0 else 0.0
    click_rate = (total_clicks / total_displays * 100.0) if total_displays > 0 else 0.0
    viewability_rate = (
        weighted_viewability / viewability_weight if viewability_weight > 0 else 0.0
    )

    ecpm_after_deduct = (
        (total_revenue_after / total_displays * 1000.0) if total_displays > 0 else 0.0
    )
    ecpm_before_deduct = (
        (total_revenue_before / total_displays * 1000.0) if total_displays > 0 else 0.0
    )

    revenue_for_cpc = total_revenue_before if for_admin else total_revenue_after
    cpc = (revenue_for_cpc / total_clicks) if total_clicks > 0 else 0.0

    return {
        "coverage_rate": round(coverage_rate, 2),
        "display_rate": round(display_rate, 2),
        "click_rate": round(click_rate, 2),
        "viewability_rate": round(viewability_rate, 2),
        "cpc": round(cpc, 4),
        "ecpm_after_deduct": round(ecpm_after_deduct, 4),
        "ecpm_before_deduct": round(ecpm_before_deduct, 4),
    }


def build_ad_data_stats_payload(
    *,
    raw: Dict[str, Any],
    total_revenue_before: float,
    for_admin: bool,
    start_date: date,
    end_date: date,
    product_id: Optional[int] = None,
    product_name: Optional[str] = None,
) -> Dict[str, Any]:
    """将聚合行转为与 Web 表格列对齐的统计字典。"""
    derived = compute_ad_data_derived_metrics(
        total_requests=float(raw["total_requests"]),
        total_matches=float(raw["total_matches"]),
        total_displays=float(raw["total_displays"]),
        total_clicks=float(raw["total_clicks"]),
        total_revenue_after=float(raw["total_revenue_after"]),
        total_revenue_before=total_revenue_before,
        total_pageviews=float(raw["total_pageviews"]),
        weighted_viewability=float(raw["weighted_viewability"]),
        viewability_weight=float(raw["viewability_weight"]),
        for_admin=for_admin,
    )

    payload: Dict[str, Any] = {
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "total_requests": int(raw["total_requests"]),
        "total_matches": int(raw["total_matches"]),
        "total_displays": int(raw["total_displays"]),
        "total_clicks": int(raw["total_clicks"]),
        "avg_coverage_rate": derived["coverage_rate"],
        "avg_display_rate": derived["display_rate"],
        "avg_click_rate": derived["click_rate"],
        "total_ecpm_after_deduct": derived["ecpm_after_deduct"],
        "total_revenue_after_deduct": round(float(raw["total_revenue_after"]), 4),
        "request_count": int(raw["total_requests"]),
        "match_count": int(raw["total_matches"]),
        "display_count": int(raw["total_displays"]),
        "click_count": int(raw["total_clicks"]),
        "pageviews": int(raw["total_pageviews"]),
        "coverage_rate": derived["coverage_rate"],
        "display_rate": derived["display_rate"],
        "click_rate": derived["click_rate"],
        "viewability_rate": derived["viewability_rate"],
        "cpc": derived["cpc"],
        "ecpm_after_deduct": derived["ecpm_after_deduct"],
        "revenue_after_deduct": round(float(raw["total_revenue_after"]), 4),
    }

    if product_id is not None:
        payload["product_id"] = product_id
        payload["product_name"] = product_name or ""

    if for_admin:
        payload.update(
            {
                "total_ecpm_before_deduct": derived["ecpm_before_deduct"],
                "total_revenue_before_deduct": round(total_revenue_before, 4),
                "ecpm_before_deduct": derived["ecpm_before_deduct"],
                "revenue_before_deduct": round(total_revenue_before, 4),
            }
        )

    return payload


def build_table_grand_total_payload(*, raw: Dict[str, Any], for_admin: bool) -> Dict[str, Any]:
    """将聚合 raw 转为与 Web 表格合计行字段对齐的字典。"""
    derived = compute_ad_data_derived_metrics(
        total_requests=float(raw["total_requests"]),
        total_matches=float(raw["total_matches"]),
        total_displays=float(raw["total_displays"]),
        total_clicks=float(raw["total_clicks"]),
        total_revenue_after=float(raw["total_revenue_after"]),
        total_revenue_before=float(raw["total_revenue_before"]),
        total_pageviews=float(raw["total_pageviews"]),
        weighted_viewability=float(raw["weighted_viewability"]),
        viewability_weight=float(raw["viewability_weight"]),
        for_admin=for_admin,
    )

    total_revenue_after = round(float(raw["total_revenue_after"]), 4)
    total_revenue_before = round(float(raw["total_revenue_before"]), 4)
    total_click = int(raw["total_clicks"])
    # 合计行 CPC 口径与历史 fetch_grand_totals 一致：始终用扣后收益，不区分管理员
    cpc = round(
        (total_revenue_after / total_click) if total_click > 0 else 0.0,
        2,
    )

    payload: Dict[str, Any] = {
        "request_count": int(raw["total_requests"]),
        "match_count": int(raw["total_matches"]),
        "display_count": int(raw["total_displays"]),
        "click_count": total_click,
        "pageviews": int(raw["total_pageviews"]),
        "coverage_rate": derived["coverage_rate"],
        "display_rate": derived["display_rate"],
        "click_rate": derived["click_rate"],
        "viewability_rate": derived["viewability_rate"],
        "ecpm_after_deduct": derived["ecpm_after_deduct"],
        "revenue_after_deduct": total_revenue_after,
        "cpc": cpc,
    }
    if for_admin:
        payload["ecpm_before_deduct"] = derived["ecpm_before_deduct"]
        payload["revenue_before_deduct"] = total_revenue_before
    return payload


def _empty_aggregate_raw() -> Dict[str, Any]:
    return {
        "total_requests": 0,
        "total_matches": 0,
        "total_displays": 0,
        "total_clicks": 0,
        "total_revenue_after": 0.0,
        "total_pageviews": 0,
        "weighted_viewability": 0.0,
        "viewability_weight": 0.0,
        "total_revenue_before": 0.0,
    }


def _row_to_aggregate_raw(row) -> Dict[str, Any]:
    """SQL 聚合行 → 统一 raw 字典。"""
    return {
        "total_requests": row.total_requests or 0,
        "total_matches": row.total_matches or 0,
        "total_displays": row.total_displays or 0,
        "total_clicks": row.total_clicks or 0,
        "total_revenue_after": float(row.total_revenue_after or 0),
        "total_pageviews": row.total_pageviews or 0,
        "weighted_viewability": float(row.weighted_viewability or 0),
        "viewability_weight": float(row.viewability_weight or 0),
        "total_revenue_before": float(getattr(row, "total_revenue_before", 0) or 0),
    }


class AdDataSummaryQuery:
    """广告数据 KPI 汇总查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch(
        self,
        current_user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        client_id: Optional[int] = None,
        product_id: Optional[int] = None,
        skip_cache: bool = False,
    ) -> Dict[str, Any]:
        cache_key = generate_cache_key(
            "ad_data_summary", current_user.id, start_date, end_date, client_id, product_id
        )
        if not skip_cache:
            cached = await get_cached(cache_key, key_prefix="ad_data")
            if cached:
                return cached

        use_assignment_table = await check_use_assignment_table(self.db)
        query = self._build_main_query(use_assignment_table, current_user, client_id, product_id, start_date, end_date)

        summary = (await self.db.execute(query)).first()
        raw = _row_to_aggregate_raw(summary) if summary else _empty_aggregate_raw()

        admin_user = is_admin(current_user)
        effective_start = start_date or (date.today() - timedelta(days=30))
        effective_end = end_date or date.today()

        response_data = build_ad_data_stats_payload(
            raw=raw,
            total_revenue_before=raw["total_revenue_before"],
            for_admin=admin_user,
            start_date=effective_start,
            end_date=effective_end,
        )

        if not skip_cache:
            await set_cached(cache_key, response_data, ttl=120, key_prefix="ad_data")
        return response_data

    async def fetch_by_product(
        self,
        current_user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        client_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        按产品分组汇总广告数据 KPI。

        Returns:
            产品统计列表，按收益(扣)降序
        """
        use_assignment_table = await check_use_assignment_table(self.db)
        query = self._build_product_group_query(
            use_assignment_table, current_user, client_id, start_date, end_date
        )
        rows = (await self.db.execute(query)).all()

        effective_start = start_date or (date.today() - timedelta(days=30))
        effective_end = end_date or date.today()
        admin_user = is_admin(current_user)

        products: List[Dict[str, Any]] = []
        for row in rows:
            raw = _row_to_aggregate_raw(row)
            if (
                raw["total_requests"] == 0
                and raw["total_matches"] == 0
                and raw["total_displays"] == 0
                and raw["total_clicks"] == 0
                and raw["total_revenue_after"] == 0
            ):
                continue

            products.append(
                build_ad_data_stats_payload(
                    raw=raw,
                    total_revenue_before=raw["total_revenue_before"],
                    for_admin=admin_user,
                    start_date=effective_start,
                    end_date=effective_end,
                    product_id=row.product_id,
                    product_name=row.product_name,
                )
            )

        products.sort(key=lambda item: item.get("revenue_after_deduct", 0), reverse=True)
        return products

    def _build_main_query(
        self,
        use_assignment_table: bool,
        current_user: User,
        client_id: Optional[int],
        product_id: Optional[int],
        start_date: Optional[date],
        end_date: Optional[date],
    ):
        query = select(*self._aggregate_select_columns())

        query = join_product_and_client(query, use_assignment_table)

        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        elif client_id:
            query = query.where(Client.id == client_id)

        query = query.where(Product.is_active == True)

        if product_id:
            query = query.where(AdData.product_id == product_id)

        return apply_date_range_filter(
            query, AdData.date, start_date, end_date, default_to_current_month=True
        )

    def _build_admin_query(
        self,
        use_assignment_table: bool,
        client_id: Optional[int],
        product_id: Optional[int],
        start_date: Optional[date],
        end_date: Optional[date],
    ):
        admin_query = select(
            func.sum(AdData.revenue_before_deduct).label("total_revenue_before"),
        )

        admin_query = join_product_and_client(admin_query, use_assignment_table)
        admin_query = admin_query.where(Product.is_active == True)

        if client_id:
            admin_query = admin_query.where(Client.id == client_id)
        if product_id:
            admin_query = admin_query.where(AdData.product_id == product_id)

        return apply_date_range_filter(
            admin_query, AdData.date, start_date, end_date, default_to_current_month=True
        )

    def _aggregate_select_columns(self):
        """公共 SUM 聚合列（含扣前收益，供产品分组复用）。"""
        return (
            func.sum(AdData.request_count).label("total_requests"),
            func.sum(AdData.match_count).label("total_matches"),
            func.sum(AdData.display_count).label("total_displays"),
            func.sum(AdData.click_count).label("total_clicks"),
            func.sum(AdData.revenue_after_deduct).label("total_revenue_after"),
            func.sum(AdData.revenue_before_deduct).label("total_revenue_before"),
            func.sum(AdData.pageviews).label("total_pageviews"),
            func.sum(
                case(
                    (
                        and_(AdData.viewability_rate > 0, AdData.click_count > 0),
                        AdData.viewability_rate * AdData.click_count,
                    ),
                    else_=0,
                )
            ).label("weighted_viewability"),
            func.sum(
                case(
                    (
                        and_(AdData.viewability_rate > 0, AdData.click_count > 0),
                        AdData.click_count,
                    ),
                    else_=0,
                )
            ).label("viewability_weight"),
        )

    def _build_product_group_query(
        self,
        use_assignment_table: bool,
        current_user: User,
        client_id: Optional[int],
        start_date: Optional[date],
        end_date: Optional[date],
    ):
        query = select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            *self._aggregate_select_columns(),
        )

        query = join_product_and_client(query, use_assignment_table)

        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        elif client_id:
            query = query.where(Client.id == client_id)

        query = query.where(Product.is_active == True)

        query = apply_date_range_filter(
            query, AdData.date, start_date, end_date, default_to_current_month=True
        )
        return query.group_by(Product.id, Product.name)
