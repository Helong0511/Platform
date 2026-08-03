"""
客户开放 API（/client_data）广告数据查询。

按 data_type 返回明细或日汇总；可选 dimension 与后台报表口径一致。
明细（all）交叉维度与日汇总选源对齐（report_type=cross / legacy 交叉形态）；
日汇总（day）见 build_daily_summary_dimension_filter。
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Optional, Tuple

from app.core.utils import normalize_date_for_ad_data

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import CLIENT_API_DEFAULT_PAGE_SIZE, CLIENT_API_MAX_PAGE_SIZE
from app.core.country_code import resolve_country_name
from app.core.query_utils import check_use_assignment_table, date_range_condition
from app.models.models import AdData, Client, CountryInfo, Product
from app.services.ad_data.queries.dimension_filter import (
    DEFAULT_DIMENSION,
    build_daily_summary_dimension_filter,
    is_cross_dimension,
    maybe_build_ad_data_dimension_filter,
    normalize_dimension,
    parse_optional_dimension,
)
from app.services.ad_data.queries.join_helpers import (
    outerjoin_best_product_assignment,
    resolved_client_id_expr,
)

logger = logging.getLogger(__name__)


def _as_decimal(value, places: int = 2) -> Decimal:
    """将 ORM/计算结果统一为指定小数位的 Decimal。"""
    quant = Decimal(10) ** -places
    if value is None:
        return Decimal(0).quantize(quant)
    if isinstance(value, Decimal):
        return value.quantize(quant, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)


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
            # 最多一条分配 + 空窗回退 Product.client_id，避免整批漏出 / JOIN 放大
            query = outerjoin_best_product_assignment(query, AdData.date)
            query = query.where(resolved_client_id_expr() == client.id)
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
                    AdData.country_code,
                    AdData.ad_unit,
                    dim,
                    ad_data_model=AdData,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            return query

        dim_filter = maybe_build_ad_data_dimension_filter(
            AdData.country_code,
            AdData.ad_unit,
            dimension,
            report_type_column=AdData.report_type,
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

        # 两阶段分页：先按 date+id 稳定取唯一 id，再回表；国家名单独查表。
        # 避免 countries / product_assignments JOIN 放大导致 LIMIT 漏行、本页条数变少。
        id_query = select(AdData.id, AdData.date).distinct()
        id_query = self._apply_client_product_scope(id_query, client, use_assignment_table)
        id_query = self._apply_date_and_dimension(id_query, start_date, end_date, dimension)
        id_query = (
            id_query.order_by(AdData.date.asc(), AdData.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        id_rows = (await self.db.execute(id_query)).all()
        page_ids = [row[0] for row in id_rows]
        if not page_ids:
            return [], total

        query = (
            select(AdData, Product.name)
            .join(Product, AdData.product_id == Product.id)
            .where(AdData.id.in_(page_ids))
            .order_by(AdData.date.asc(), AdData.id.asc())
        )
        rows = (await self.db.execute(query)).all()

        country_codes = {
            (ad_data.country_code or "").strip()
            for ad_data, _ in rows
            if (ad_data.country_code or "").strip()
        }
        country_name_map = await self._load_country_name_zh(country_codes)

        result: list[dict[str, Any]] = []
        for ad_data, product_name in rows:
            date_obj = normalize_date_for_ad_data(ad_data.date)
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
            viewability_rate = (
                ad_data.viewability_rate if ad_data.viewability_rate is not None else Decimal('0')
            )
            country_code_str = ad_data.country_code or ""
            country_name_zh = country_name_map.get(country_code_str)

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
                    "coverage_rate": _as_decimal(coverage_rate),
                    "display_count": int(ad_data.display_count),
                    "display_rate": _as_decimal(display_rate),
                    "click_count": int(ad_data.click_count),
                    "click_rate": _as_decimal(click_rate),
                    "viewability_rate": _as_decimal(viewability_rate),
                    "cpc": _as_decimal(ad_data.cpc),
                    "pageviews": int(ad_data.pageviews or 0),
                    "ecpm": _as_decimal(ad_data.ecpm_after_deduct),
                    "revenue": _as_decimal(ad_data.revenue_after_deduct),
                }
            )
        return result, total

    async def _load_country_name_zh(self, country_codes: set[str]) -> dict[str, str]:
        """按国家码批量取中文名；同码多行时取第一条，避免 JOIN 放大。"""
        if not country_codes:
            return {}
        rows = (
            await self.db.execute(
                select(CountryInfo.alpha_2_code, CountryInfo.country_name_zh).where(
                    CountryInfo.alpha_2_code.in_(country_codes)
                )
            )
        ).all()
        out: dict[str, str] = {}
        for code, name in rows:
            key = (code or "").strip()
            if key and key not in out and name:
                out[key] = name
        return out

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
        # 排序键需覆盖分组维度，否则同产品多广告单元/国家时 OFFSET 翻页会漏/重
        order_cols = [subq.c.date.asc(), subq.c.product_id.asc()]
        if hasattr(subq.c, "ad_unit"):
            order_cols.append(subq.c.ad_unit.asc())
        if hasattr(subq.c, "country_code"):
            order_cols.append(subq.c.country_code.asc())
        page_query = select(subq).order_by(*order_cols).offset(offset).limit(page_size)
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
        """
        兼容旧版：仍按 date+product+ad_unit 分组，但互斥选源（默认 country），
        避免双 API 多来源行被 SUM 重复统计。
        """
        query = select(
            AdData.date.label("date"),
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
        query = self._apply_date_and_dimension(
            query, start_date, end_date, DEFAULT_DIMENSION, daily_summary=True
        )
        query = query.group_by(
            AdData.date,
            Product.id,
            Product.name,
            AdData.ad_unit,
        ).order_by(AdData.date.asc(), Product.id.asc(), AdData.ad_unit.asc())

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
        dim = normalize_dimension(dimension)
        group_by_ad_unit = dim == "ad_unit" or is_cross_dimension(dim)
        group_by_country = dim == "country" or is_cross_dimension(dim)

        select_cols: list[Any] = [
            AdData.date.label("date"),
            Product.id.label("product_id"),
            Product.name.label("product_name"),
        ]
        group_cols: list[Any] = [
            AdData.date,
            Product.id,
            Product.name,
        ]

        if group_by_ad_unit:
            select_cols.append(AdData.ad_unit.label("ad_unit"))
            group_cols.append(AdData.ad_unit)
        if group_by_country:
            select_cols.append(AdData.country_code.label("country_code"))
            group_cols.append(AdData.country_code)

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
            query, start_date, end_date, dim, daily_summary=True
        )
        order_cols: list[Any] = [AdData.date.asc(), Product.id.asc()]
        if group_by_ad_unit:
            order_cols.append(AdData.ad_unit.asc())
        if group_by_country:
            order_cols.append(AdData.country_code.asc())
        query = query.group_by(*group_cols).order_by(*order_cols)

        rows, total = await self._paginate_grouped_query(query, offset, page_size)
        country_codes = {
            (getattr(row, "country_code", None) or "").strip()
            for row in rows
            if (getattr(row, "country_code", None) or "").strip()
        }
        country_name_map = await self._load_country_name_zh(country_codes)
        return [
            self._daily_row_to_dict(row, dim=dim, country_name_map=country_name_map)
            for row in rows
        ], total

    def _daily_row_to_dict(
        self,
        row: Any,
        dim: Optional[str],
        country_name_map: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        date_obj = normalize_date_for_ad_data(row.date)
        date_str = date_obj.isoformat()

        total_request_count = int(row.request_count or 0)
        total_match_count = int(row.match_count or 0)
        total_display_count = int(row.display_count or 0)
        total_click_count = int(row.click_count or 0)
        total_viewability_rate = _as_decimal(row.viewability_rate)
        total_pageviews = int(row.pageviews or 0)
        total_revenue = _as_decimal(row.revenue)

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

        if dim is None or dim == "ad_unit":
            ad_unit = getattr(row, "ad_unit", "") or ""
            country_code = "ZZ"
            country_name_zh = "全部区域"
        elif dim == "country" or is_cross_dimension(dim):
            ad_unit = getattr(row, "ad_unit", "") or "" if is_cross_dimension(dim) else ""
            country_code = (getattr(row, "country_code", None) or "").strip() or "ZZ"
            mapped = (country_name_map or {}).get(country_code)
            country_name_zh = mapped or resolve_country_name(None, country_code) or "全部区域"
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
            "coverage_rate": _as_decimal(coverage_rate),
            "display_count": total_display_count,
            "display_rate": _as_decimal(display_rate),
            "click_count": total_click_count,
            "click_rate": _as_decimal(click_rate),
            "viewability_rate": total_viewability_rate,
            "cpc": _as_decimal(cpc),
            "pageviews": total_pageviews,
            "ecpm": _as_decimal(ecpm),
            "revenue": total_revenue,
        }
