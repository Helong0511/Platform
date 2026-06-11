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
from typing import Any, Dict, Optional

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
    ) -> Dict[str, Any]:
        cache_key = generate_cache_key(
            "ad_data_summary", current_user.id, start_date, end_date, client_id, product_id
        )
        cached = await get_cached(cache_key, key_prefix="ad_data")
        if cached:
            return cached

        use_assignment_table = await check_use_assignment_table(self.db)
        query = self._build_main_query(use_assignment_table, current_user, client_id, product_id, start_date, end_date)

        summary = (await self.db.execute(query)).first()
        if summary is None:
            raw = {
                "total_requests": 0,
                "total_matches": 0,
                "total_displays": 0,
                "total_clicks": 0,
                "total_revenue_after": 0.0,
                "total_pageviews": 0,
                "weighted_viewability": 0.0,
                "viewability_weight": 0.0,
            }
        else:
            raw = {
                "total_requests": summary.total_requests or 0,
                "total_matches": summary.total_matches or 0,
                "total_displays": summary.total_displays or 0,
                "total_clicks": summary.total_clicks or 0,
                "total_revenue_after": float(summary.total_revenue_after or 0),
                "total_pageviews": summary.total_pageviews or 0,
                "weighted_viewability": float(summary.weighted_viewability or 0),
                "viewability_weight": float(summary.viewability_weight or 0),
            }

        total_revenue_before = 0.0
        admin_user = is_admin(current_user)
        if admin_user:
            admin_query = self._build_admin_query(
                use_assignment_table, client_id, product_id, start_date, end_date
            )
            admin_summary = (await self.db.execute(admin_query)).first()
            if admin_summary:
                total_revenue_before = float(admin_summary.total_revenue_before or 0)

        derived = compute_ad_data_derived_metrics(
            total_requests=float(raw["total_requests"]),
            total_matches=float(raw["total_matches"]),
            total_displays=float(raw["total_displays"]),
            total_clicks=float(raw["total_clicks"]),
            total_revenue_after=raw["total_revenue_after"],
            total_revenue_before=total_revenue_before,
            total_pageviews=float(raw["total_pageviews"]),
            weighted_viewability=raw["weighted_viewability"],
            viewability_weight=raw["viewability_weight"],
            for_admin=admin_user,
        )

        effective_start = start_date or (date.today() - timedelta(days=30))
        effective_end = end_date or date.today()

        response_data: Dict[str, Any] = {
            "date_range": {
                "start_date": effective_start,
                "end_date": effective_end,
            },
            # 兼容旧字段
            "total_requests": int(raw["total_requests"]),
            "total_matches": int(raw["total_matches"]),
            "total_displays": int(raw["total_displays"]),
            "total_clicks": int(raw["total_clicks"]),
            "avg_coverage_rate": derived["coverage_rate"],
            "avg_display_rate": derived["display_rate"],
            "avg_click_rate": derived["click_rate"],
            "total_ecpm_after_deduct": derived["ecpm_after_deduct"],
            "total_revenue_after_deduct": round(raw["total_revenue_after"], 4),
            # 与 Web 表格列名对齐
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
            "revenue_after_deduct": round(raw["total_revenue_after"], 4),
        }

        if admin_user:
            response_data.update(
                {
                    "total_ecpm_before_deduct": derived["ecpm_before_deduct"],
                    "total_revenue_before_deduct": round(total_revenue_before, 4),
                    "ecpm_before_deduct": derived["ecpm_before_deduct"],
                    "revenue_before_deduct": round(total_revenue_before, 4),
                }
            )

        await set_cached(cache_key, response_data, ttl=120, key_prefix="ad_data")
        return response_data

    def _build_main_query(
        self,
        use_assignment_table: bool,
        current_user: User,
        client_id: Optional[int],
        product_id: Optional[int],
        start_date: Optional[date],
        end_date: Optional[date],
    ):
        query = select(
            func.sum(AdData.request_count).label("total_requests"),
            func.sum(AdData.match_count).label("total_matches"),
            func.sum(AdData.display_count).label("total_displays"),
            func.sum(AdData.click_count).label("total_clicks"),
            func.sum(AdData.revenue_after_deduct).label("total_revenue_after"),
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
