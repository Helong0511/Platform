"""
客户开放 API（/client_data）广告数据查询。

按 data_type 返回明细或日汇总；可选 dimension 与后台报表口径一致。
未传 dimension 时保持历史行为（返回库中全部匹配行，可能含重复统计风险）。
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, List, Optional, Tuple

from sqlalchemy import and_, func, literal_column, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import CLIENT_API_DEFAULT_PAGE_SIZE, CLIENT_API_MAX_PAGE_SIZE
from app.core.query_utils import check_use_assignment_table, date_range_condition
from app.models.models import AdData, Client, CountryInfo, Product, ProductAssignment
from app.services.ad_data.queries.dimension_filter import (
    CROSS_DIMENSION,
    build_daily_summary_dimension_filter,
    is_cross_dimension,
    maybe_build_ad_data_dimension_filter,
    normalize_dimension,
    parse_optional_dimension,
)

logger = logging.getLogger(__name__)


class ClientAdDataQuery:
    """客户 API 广告数据查询（无 User 会话，按 Client 过滤）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch(
        self,
        client: Client,
        start_date: date,
        end_date: date,
        data_type: str,
        dimension: Optional[str] = None,
        page: int = 1,
        page_size: int = CLIENT_API_DEFAULT_PAGE_SIZE,
    ) -> tuple[list[dict[str, Any]], int]:
        """查询并返回 (可映射为 AdDataItemResponse 的字典列表, 总条数)。"""
        page_size = min(max(1, page_size), CLIENT_API_MAX_PAGE_SIZE)
        page = max(1, page)
        offset = (page - 1) * page_size

        use_assignment_table = await check_use_assignment_table(self.db)
        dim = parse_optional_dimension(dimension)

        if data_type == "day":
            return await self._fetch_daily_summary(
                client, start_date, end_date, use_assignment_table, dim, offset, page_size
            )
        return await self._fetch_detail(
            client, start_date, end_date, use_assignment_table, dim, offset, page_size
        )

    def _apply_client_product_scope(self, query, client: Client, use_assignment_table: bool):
        query = query.join(Product, AdData.product_id == Product.id)
        query = query.where(Product.is_active == True)

        if use_assignment_table:
            end_date_with_default = func.coalesce(
                func.date_add(ProductAssignment.end_date, text("INTERVAL 1 DAY")),
                literal_column("'2099-12-31'"),
            )
            query = query.join(
                ProductAssignment,
                and_(
                    ProductAssignment.product_id == Product.id,
                    AdData.date >= ProductAssignment.start_date,
                    AdData.date < end_date_with_default,
                ),
            )
            query = query.where(ProductAssignment.client_id == client.id)
        else:
            query = query.where(Product.client_id == client.id)
        return query

    def _apply_date_and_dimension(
        self,
        query,
        start_date: date,
        end_date: date,
        dimension: Optional[str],
        *,
        daily_summary: bool = False,
    ):
        date_condition = date_range_condition(AdData.date, start_date, end_date)
        if date_condition is not None:
            query = query.where(date_condition)

        if daily_summary and dimension:
            dim = normalize_dimension(dimension)
            query = query.where(
                build_daily_summary_dimension_filter(
                    AdData.country_code, AdData.ad_unit, dim
                )
            )
            return query

        dim_filter = maybe_build_ad_data_dimension_filter(
            AdData.country_code, AdData.ad_unit, dimension
        )
        if dim_filter is not None:
            query = query.where(dim_filter)
        return query

    async def _count_scoped_rows(
        self,
        client: Client,
        start_date: date,
        end_date: date,
        use_assignment_table: bool,
        dimension: Optional[str],
    ) -> int:
        count_query = select(func.count(AdData.id))
        count_query = self._apply_client_product_scope(count_query, client, use_assignment_table)
        count_query = self._apply_date_and_dimension(count_query, start_date, end_date, dimension)
        return int((await self.db.execute(count_query)).scalar() or 0)

    async def _fetch_detail(
        self,
        client: Client,
        start_date: date,
        end_date: date,
        use_assignment_table: bool,
        dimension: Optional[str],
        offset: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        total = await self._count_scoped_rows(
            client, start_date, end_date, use_assignment_table, dimension
        )

        query = select(AdData, Product.name, CountryInfo.country_name_zh)
        query = self._apply_client_product_scope(query, client, use_assignment_table)
        query = query.outerjoin(
            CountryInfo,
            AdData.country_code.collate("utf8mb4_unicode_ci")
            == CountryInfo.alpha_2_code.collate("utf8mb4_unicode_ci"),
        )
        query = self._apply_date_and_dimension(query, start_date, end_date, dimension)
        query = query.order_by(AdData.date.asc()).offset(offset).limit(page_size)

        rows = (await self.db.execute(query)).all()

        result: list[dict[str, Any]] = []
        for row in rows:
            ad_data, product_name, country_name_zh = row[0], row[1], row[2]

            date_obj = ad_data.date.date() if hasattr(ad_data.date, "date") else ad_data.date
            date_str = date_obj.isoformat()

            coverage_rate = (
                ad_data.coverage_rate
                if ad_data.coverage_rate is not None
                else round(
                    (ad_data.match_count / ad_data.request_count * 100)
                    if ad_data.request_count > 0
                    else 0.0,
                    2,
                )
            )
            display_rate = (
                ad_data.display_rate
                if ad_data.display_rate is not None
                else round(
                    (ad_data.display_count / ad_data.match_count * 100)
                    if ad_data.match_count > 0
                    else 0.0,
                    2,
                )
            )
            click_rate = (
                ad_data.click_rate
                if ad_data.click_rate is not None
                else round(
                    (ad_data.click_count / ad_data.display_count * 100)
                    if ad_data.display_count > 0
                    else 0.0,
                    2,
                )
            )
            viewability_rate = ad_data.viewability_rate if ad_data.viewability_rate is not None else 0.0
            country_code_str = ad_data.country_code or ""

            if country_name_zh:
                final_country_name = country_name_zh
            elif not ad_data.country_code:
                final_country_name = ""
            elif ad_data.country_code == "AA":
                final_country_name = "未知区域"
            elif ad_data.country_code == "ZZ":
                final_country_name = "全部区域"
            else:
                final_country_name = ""

            result.append(
                {
                    "date": date_str,
                    "product_name": product_name or "",
                    "ad_unit": ad_data.ad_unit or "",
                    "country_code": country_code_str,
                    "country_name_zh": final_country_name,
                    "request_count": int(ad_data.request_count),
                    "match_count": int(ad_data.match_count),
                    "coverage_rate": float(coverage_rate),
                    "display_count": int(ad_data.display_count),
                    "display_rate": float(display_rate),
                    "click_count": int(ad_data.click_count),
                    "click_rate": float(click_rate),
                    "viewability_rate": float(round(viewability_rate, 2)),
                    "cpc": float(round(ad_data.cpc or 0.0, 2)),
                    "pageviews": int(ad_data.pageviews or 0),
                    "ecpm": float(round(ad_data.ecpm_after_deduct, 2)),
                    "revenue": float(round(ad_data.revenue_after_deduct, 2)),
                }
            )
        return result, total

    async def _fetch_daily_summary(
        self,
        client: Client,
        start_date: date,
        end_date: date,
        use_assignment_table: bool,
        dimension: Optional[str],
        offset: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        if dimension is None:
            return await self._fetch_daily_summary_legacy(
                client, start_date, end_date, use_assignment_table, offset, page_size
            )
        return await self._fetch_daily_summary_by_dimension(
            client, start_date, end_date, use_assignment_table, dimension, offset, page_size
        )

    async def _paginate_grouped_query(
        self,
        query,
        offset: int,
        page_size: int,
    ) -> tuple[list[Any], int]:
        """对分组聚合结果分页：总数与当前页均基于同一 subquery。"""
        subq = query.subquery()
        total = int((await self.db.execute(select(func.count()).select_from(subq))).scalar() or 0)
        page_query = (
            select(subq)
            .order_by(subq.c.date.asc(), subq.c.product_id.asc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(page_query)).all()
        return rows, total

    async def _fetch_daily_summary_legacy(
        self,
        client: Client,
        start_date: date,
        end_date: date,
        use_assignment_table: bool,
        offset: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        query = select(
            func.date(AdData.date).label("date"),
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            AdData.ad_unit.label("ad_unit"),
            func.sum(AdData.request_count).label("request_count"),
            func.sum(AdData.match_count).label("match_count"),
            func.sum(AdData.display_count).label("display_count"),
            func.sum(AdData.click_count).label("click_count"),
            func.avg(AdData.viewability_rate).label("viewability_rate"),
            func.sum(AdData.pageviews).label("pageviews"),
            func.sum(AdData.revenue_after_deduct).label("revenue"),
        )
        query = self._apply_client_product_scope(query, client, use_assignment_table)
        query = self._apply_date_and_dimension(query, start_date, end_date, None)
        query = query.group_by(
            func.date(AdData.date),
            Product.id,
            Product.name,
            AdData.ad_unit,
        ).order_by(func.date(AdData.date).asc(), Product.id.asc())

        rows, total = await self._paginate_grouped_query(query, offset, page_size)
        return [self._daily_row_to_dict(row, dim=None) for row in rows], total

    async def _fetch_daily_summary_by_dimension(
        self,
        client: Client,
        start_date: date,
        end_date: date,
        use_assignment_table: bool,
        dimension: str,
        offset: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        group_by_ad_unit = dimension == "ad_unit" or is_cross_dimension(dimension)

        select_cols: list[Any] = [
            func.date(AdData.date).label("date"),
            Product.id.label("product_id"),
            Product.name.label("product_name"),
        ]
        group_cols: list[Any] = [
            func.date(AdData.date),
            Product.id,
            Product.name,
        ]

        if group_by_ad_unit:
            select_cols.append(AdData.ad_unit.label("ad_unit"))
            group_cols.append(AdData.ad_unit)

        query = select(
            *select_cols,
            func.sum(AdData.request_count).label("request_count"),
            func.sum(AdData.match_count).label("match_count"),
            func.sum(AdData.display_count).label("display_count"),
            func.sum(AdData.click_count).label("click_count"),
            func.avg(AdData.viewability_rate).label("viewability_rate"),
            func.sum(AdData.pageviews).label("pageviews"),
            func.sum(AdData.revenue_after_deduct).label("revenue"),
        )
        query = self._apply_client_product_scope(query, client, use_assignment_table)
        query = self._apply_date_and_dimension(
            query, start_date, end_date, dimension, daily_summary=True
        )
        query = query.group_by(*group_cols).order_by(
            func.date(AdData.date).asc(), Product.id.asc()
        )

        rows, total = await self._paginate_grouped_query(query, offset, page_size)
        return [self._daily_row_to_dict(row, dim=dimension) for row in rows], total

    def _daily_row_to_dict(
        self,
        row: Any,
        dim: Optional[str],
    ) -> dict[str, Any]:
        date_obj = row.date if isinstance(row.date, date) else row.date.date()
        date_str = date_obj.isoformat()

        total_request_count = int(row.request_count or 0)
        total_match_count = int(row.match_count or 0)
        total_display_count = int(row.display_count or 0)
        total_click_count = int(row.click_count or 0)
        total_viewability_rate = float(row.viewability_rate or 0.0)
        total_pageviews = int(row.pageviews or 0)
        total_revenue = float(row.revenue or 0.0)

        coverage_rate = round(
            (total_match_count / total_request_count * 100) if total_request_count > 0 else 0.0,
            2,
        )
        display_rate = round(
            (total_display_count / total_match_count * 100) if total_match_count > 0 else 0.0,
            2,
        )
        click_rate = round(
            (total_click_count / total_display_count * 100) if total_display_count > 0 else 0.0,
            2,
        )
        cpc = round((total_revenue / total_click_count) if total_click_count > 0 else 0.0, 2)
        ecpm = round((total_revenue / total_display_count * 1000) if total_display_count > 0 else 0.0, 2)

        if dim is None:
            ad_unit = row.ad_unit or ""
            country_code = "ZZ"
            country_name_zh = "全部区域"
        elif dim in ("country", "ad_unit", CROSS_DIMENSION):
            ad_unit = getattr(row, "ad_unit", "") or "" if dim != "country" else ""
            country_code = "ZZ"
            country_name_zh = "全部区域"
        else:
            ad_unit = getattr(row, "ad_unit", "") or ""
            country_code = "ZZ"
            country_name_zh = "全部区域"

        return {
            "date": date_str,
            "product_name": row.product_name or "",
            "ad_unit": ad_unit,
            "country_code": country_code,
            "country_name_zh": country_name_zh,
            "request_count": total_request_count,
            "match_count": total_match_count,
            "coverage_rate": float(coverage_rate),
            "display_count": total_display_count,
            "display_rate": float(display_rate),
            "click_count": total_click_count,
            "click_rate": float(click_rate),
            "viewability_rate": round(total_viewability_rate, 2),
            "cpc": float(cpc),
            "pageviews": total_pageviews,
            "ecpm": float(ecpm),
            "revenue": round(total_revenue, 2),
        }
