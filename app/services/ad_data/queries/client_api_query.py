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
from typing import Any, Optional

from app.core.utils import normalize_date_for_ad_data

from sqlalchemy import and_, case, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased

from app.core.constants import (
    CLIENT_API_DEFAULT_PAGE_SIZE,
    CLIENT_API_MAX_PAGE,
    CLIENT_API_MAX_PAGE_SIZE,
)
from app.core.country_code import ALL_REGIONS_COUNTRY_CODE, resolve_country_name
from app.core.query_utils import check_use_assignment_table, date_range_condition
from app.models.models import AdData, Client, CountryInfo, Product
from app.services.ad_data.queries.dimension_filter import (
    DEFAULT_DIMENSION,
    DETAIL_ALL_DIMENSION,
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
        page = min(max(1, page), CLIENT_API_MAX_PAGE)
        offset = (page - 1) * page_size

        use_assignment_table = await check_use_assignment_table(self.db)
        dim = parse_optional_dimension(dimension)
        if data_type == "day" and dim == DETAIL_ALL_DIMENSION:
            raise ValueError("data_type='day' 不支持 dimension='all'")
        if data_type != "day" and dim is None:
            dim = DEFAULT_DIMENSION

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
            # 重叠脏数据仍按全局一致的最小分配 ID 唯一归属，禁止按请求客户
            # 动态选取，否则同一条数据会同时暴露给多个客户。
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
            return self._apply_country_identity_dedup(query)

        dim_filter = maybe_build_ad_data_dimension_filter(
            AdData.country_code,
            AdData.ad_unit,
            dimension,
            report_type_column=AdData.report_type,
        )
        if dim_filter is not None:
            query = query.where(dim_filter)
        return self._apply_country_identity_dedup(query)

    @staticmethod
    def _apply_country_identity_dedup(query):
        """按规范化国家/广告单元逻辑键去重，仅让可能冲突的脏行进入子查询。"""
        duplicate = aliased(AdData)
        current_trimmed_country = func.trim(AdData.country_code)
        duplicate_trimmed_country = func.trim(duplicate.country_code)
        current_country_key = func.coalesce(
            func.nullif(current_trimmed_country, ALL_REGIONS_COUNTRY_CODE),
            "",
        )
        duplicate_country_key = func.coalesce(
            func.nullif(duplicate_trimmed_country, ALL_REGIONS_COUNTRY_CODE),
            "",
        )
        current_trimmed_ad_unit = func.trim(AdData.ad_unit)
        duplicate_trimmed_ad_unit = func.trim(duplicate.ad_unit)
        current_ad_unit_key = func.coalesce(current_trimmed_ad_unit, "")
        duplicate_ad_unit_key = func.coalesce(duplicate_trimmed_ad_unit, "")
        duplicate_clean_identity = and_(
            duplicate.country_code.isnot(None),
            duplicate_trimmed_country != "",
            duplicate_trimmed_country != ALL_REGIONS_COUNTRY_CODE,
            func.char_length(duplicate.country_code)
            == func.char_length(duplicate_trimmed_country),
            func.char_length(duplicate.ad_unit)
            == func.char_length(duplicate_trimmed_ad_unit),
        )
        canonical_id = (
            select(duplicate.id)
            .where(
                and_(
                    duplicate.date == AdData.date,
                    duplicate.product_id == AdData.product_id,
                    duplicate_country_key == current_country_key,
                    duplicate_ad_unit_key == current_ad_unit_key,
                    duplicate.data_source.is_not_distinct_from(AdData.data_source),
                    duplicate.report_type.is_not_distinct_from(AdData.report_type),
                    duplicate.upstream_account.is_not_distinct_from(AdData.upstream_account),
                )
            )
            .order_by(
                case((duplicate_clean_identity, 0), else_=1),
                duplicate.id.asc(),
            )
            .limit(1)
            .correlate(AdData)
            .scalar_subquery()
        )
        # 正常具体国家 + 无首尾空格广告单元受唯一键完整保护，可直接放行；
        # 脏行的 canonical_id 优先指向同组干净行，不存在干净行时再取最小 ID。
        clean_unique_identity = and_(
            AdData.country_code.isnot(None),
            current_trimmed_country != "",
            current_trimmed_country != ALL_REGIONS_COUNTRY_CODE,
            func.char_length(AdData.country_code) == func.char_length(current_trimmed_country),
            func.char_length(AdData.ad_unit) == func.char_length(current_trimmed_ad_unit),
        )
        return query.where(or_(clean_unique_identity, AdData.id == canonical_id))

    async def _count_scoped_rows(
        self,
        client: Client,
        start_date: date,
        end_date: date,
        use_assignment_table: bool,
        dimension: Optional[str],
    ) -> int:
        count_query = select(func.count(func.distinct(AdData.id)))
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
        # 单条 SQL 完成过滤、排序、分页和 total 统计，避免 COUNT、取 ID、回表之间
        # 的一致性窗口。分配辅助 JOIN 已保证每条 AdData 最多匹配一条记录。
        total_col = func.count().over().label("_total")
        query = select(AdData, Product.name, total_col)
        query = self._apply_client_product_scope(query, client, use_assignment_table)
        query = self._apply_date_and_dimension(query, start_date, end_date, dimension)
        query = query.order_by(AdData.date.asc(), AdData.id.asc()).offset(offset).limit(page_size)
        raw_rows = (await self.db.execute(query)).all()
        if raw_rows:
            total = int(raw_rows[0][2] or 0)
            rows = [(row[0], row[1]) for row in raw_rows]
        else:
            # 超出最后一页时窗口查询没有行，补一次 total，保持分页协议完整。
            total = await self._count_scoped_rows(
                client, start_date, end_date, use_assignment_table, dimension
            )
            rows = []
        if not rows:
            return [], total

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
            request_count = int(ad_data.request_count or 0)
            match_count = int(ad_data.match_count or 0)
            display_count = int(ad_data.display_count or 0)
            click_count = int(ad_data.click_count or 0)

            coverage_rate = (
                ad_data.coverage_rate
                if ad_data.coverage_rate is not None
                else round(
                    (match_count / request_count * 100)
                    if request_count > 0
                    else 0.0,
                    2,
                )
            )
            display_rate = (
                ad_data.display_rate
                if ad_data.display_rate is not None
                else round(
                    (display_count / match_count * 100)
                    if match_count > 0
                    else 0.0,
                    2,
                )
            )
            click_rate = (
                ad_data.click_rate
                if ad_data.click_rate is not None
                else round(
                    (click_count / display_count * 100)
                    if display_count > 0
                    else 0.0,
                    2,
                )
            )
            viewability_rate = (
                ad_data.viewability_rate if ad_data.viewability_rate is not None else Decimal('0')
            )
            country_code_str = (ad_data.country_code or "").strip()
            country_name_zh = country_name_map.get(country_code_str)

            if country_name_zh:
                final_country_name = country_name_zh
            elif not country_code_str:
                final_country_name = ""
            elif country_code_str == "AA":
                final_country_name = "未知区域"
            elif country_code_str == "ZZ":
                final_country_name = "全部区域"
            else:
                final_country_name = ""

            result.append(
                {
                    "id": int(ad_data.id),
                    "product_id": int(ad_data.product_id),
                    "date": date_str,
                    "product_name": product_name or "",
                    "ad_unit": (ad_data.ad_unit or "").strip(),
                    "country_code": country_code_str,
                    "country_name_zh": final_country_name,
                    "request_count": request_count,
                    "match_count": match_count,
                    "coverage_rate": _as_decimal(coverage_rate),
                    "display_count": display_count,
                    "display_rate": _as_decimal(display_rate),
                    "click_count": click_count,
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
        """对分组聚合结果分页：非空页用单条窗口查询同时返回 total。"""
        subq = query.order_by(None).subquery()
        # 排序键需覆盖分组维度，否则同产品多广告单元/国家时 OFFSET 翻页会漏/重
        order_cols = [subq.c.date.asc(), subq.c.product_id.asc()]
        if hasattr(subq.c, "ad_unit"):
            order_cols.append(subq.c.ad_unit.asc())
        if hasattr(subq.c, "country_code"):
            order_cols.append(subq.c.country_code.asc())
        total_col = func.count().over().label("_total")
        page_query = select(subq, total_col).order_by(*order_cols).offset(offset).limit(page_size)
        rows = (await self.db.execute(page_query)).all()
        if rows:
            return rows, int(rows[0]._total or 0)
        # 超出最后一页时窗口查询没有行，补查 total 以保持分页协议完整。
        total = int((await self.db.execute(select(func.count()).select_from(subq))).scalar() or 0)
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
        ad_unit_group_expr = func.trim(AdData.ad_unit)
        query = select(
            AdData.date.label("date"),
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            ad_unit_group_expr.label("ad_unit"),
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
            ad_unit_group_expr,
        ).order_by(AdData.date.asc(), Product.id.asc(), ad_unit_group_expr.asc())

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

        ad_unit_group_expr = func.trim(AdData.ad_unit)
        if group_by_ad_unit:
            select_cols.append(ad_unit_group_expr.label("ad_unit"))
            group_cols.append(ad_unit_group_expr)
        trimmed_country = func.trim(AdData.country_code)
        country_group_expr = func.coalesce(
            func.nullif(trimmed_country, ""),
            ALL_REGIONS_COUNTRY_CODE,
        )
        if group_by_country:
            select_cols.append(country_group_expr.label("country_code"))
            group_cols.append(country_group_expr)

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
            order_cols.append(ad_unit_group_expr.asc())
        if group_by_country:
            order_cols.append(country_group_expr.asc())
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
            ad_unit = (getattr(row, "ad_unit", "") or "").strip()
            country_code = "ZZ"
            country_name_zh = "全部区域"
        elif dim == "country" or is_cross_dimension(dim):
            ad_unit = (
                (getattr(row, "ad_unit", "") or "").strip()
                if is_cross_dimension(dim)
                else ""
            )
            country_code = (getattr(row, "country_code", None) or "").strip() or "ZZ"
            mapped = (country_name_map or {}).get(country_code)
            country_name_zh = mapped or resolve_country_name(None, country_code) or "全部区域"
        else:
            ad_unit = (getattr(row, "ad_unit", "") or "").strip()
            country_code = "ZZ"
            country_name_zh = "全部区域"

        return {
            "product_id": int(row.product_id) if getattr(row, "product_id", None) is not None else None,
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
