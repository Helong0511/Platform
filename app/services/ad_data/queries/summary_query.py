"""
广告数据 KPI 汇总查询。

功能说明：
- 对匹配记录做 SUM 聚合，计算漏斗总量与平均转化率
- 管理员额外查询减扣前 eCPM/收入；结果带 Redis 缓存

在系统中的位置：
- 被 ``AdDataService.get_ad_data_summary`` 调用
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import Float, case, func
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
            totals = {
                "total_requests": 0,
                "total_matches": 0,
                "total_displays": 0,
                "total_clicks": 0,
                "total_ecpm_after": 0,
                "total_revenue_after": 0,
                "avg_coverage_rate": 0,
                "avg_display_rate": 0,
                "avg_click_rate": 0,
            }
        else:
            totals = {
                "total_requests": summary.total_requests or 0,
                "total_matches": summary.total_matches or 0,
                "total_displays": summary.total_displays or 0,
                "total_clicks": summary.total_clicks or 0,
                "total_ecpm_after": summary.total_ecpm_after or 0,
                "total_revenue_after": summary.total_revenue_after or 0,
                "avg_coverage_rate": summary.avg_coverage_rate or 0,
                "avg_display_rate": summary.avg_display_rate or 0,
                "avg_click_rate": summary.avg_click_rate or 0,
            }

        total_ecpm_before = 0
        total_revenue_before = 0
        if is_admin(current_user):
            admin_query = self._build_admin_query(
                use_assignment_table, client_id, product_id, start_date, end_date
            )
            admin_summary = (await self.db.execute(admin_query)).first()
            if admin_summary:
                total_ecpm_before = admin_summary.total_ecpm_before or 0
                total_revenue_before = admin_summary.total_revenue_before or 0

        response_data = {
            "date_range": {
                "start_date": start_date or (date.today() - timedelta(days=30)),
                "end_date": end_date or date.today(),
            },
            "total_requests": totals["total_requests"],
            "total_matches": totals["total_matches"],
            "total_displays": totals["total_displays"],
            "total_clicks": totals["total_clicks"],
            "avg_coverage_rate": round(totals["avg_coverage_rate"], 4),
            "avg_display_rate": round(totals["avg_display_rate"], 4),
            "avg_click_rate": round(totals["avg_click_rate"], 4),
            "total_ecpm_after_deduct": round(totals["total_ecpm_after"], 4),
            "total_revenue_after_deduct": round(totals["total_revenue_after"], 4),
        }

        if current_user.role == "admin":
            response_data.update(
                {
                    "total_ecpm_before_deduct": round(total_ecpm_before, 4),
                    "total_revenue_before_deduct": round(total_revenue_before, 4),
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
            func.sum(AdData.ecpm_after_deduct).label("total_ecpm_after"),
            func.sum(AdData.revenue_after_deduct).label("total_revenue_after"),
            func.coalesce(
                func.avg(AdData.coverage_rate),
                case(
                    (func.sum(AdData.request_count) == 0, 0),
                    else_=func.cast(func.sum(AdData.match_count), Float)
                    * 100.0
                    / func.cast(func.sum(AdData.request_count), Float),
                ),
            ).label("avg_coverage_rate"),
            func.coalesce(
                func.avg(AdData.display_rate),
                case(
                    (func.sum(AdData.match_count) == 0, 0),
                    else_=func.cast(func.sum(AdData.display_count), Float)
                    * 100.0
                    / func.cast(func.sum(AdData.match_count), Float),
                ),
            ).label("avg_display_rate"),
            func.coalesce(
                func.avg(AdData.click_rate),
                case(
                    (func.sum(AdData.display_count) == 0, 0),
                    else_=func.cast(func.sum(AdData.click_count), Float)
                    * 100.0
                    / func.cast(func.sum(AdData.display_count), Float),
                ),
            ).label("avg_click_rate"),
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
            func.sum(AdData.ecpm_before_deduct).label("total_ecpm_before"),
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
