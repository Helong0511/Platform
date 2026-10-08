"""
广告数据每日汇总查询构建器。

功能说明：
- 按统计维度分组聚合：按国家→日期+产品（可选 split_by_country 按国家分行）；
  按广告单元→日期+产品+广告单元；按广告单元+国家→日期+产品+广告单元+国家
- 支持权限过滤、分页、SQL/内存混合排序
- Redis 缓存（默认 600s，可 env 配置），与 KPI summary 共用 ad_data 失效前缀
- 冷路径同 key 单飞（进程内合并 + 跨 Worker 锁等待），减轻缓存击穿
- 列表查询用 COUNT(*) OVER() 带回分组总数，避免再跑一遍 GROUP BY 计数
- 全量合计独立缓存，并与列表查询并行执行，降低冷路径墙钟时间

在系统中的位置：
    - 被 ``AdDataService.get_daily_summary`` 调用
"""
import asyncio
import logging
from calendar import monthrange
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import ECPM_MULTIPLIER, PERCENTAGE_MULTIPLIER
from app.core.database import AsyncSessionLocal
from app.core.utils import normalize_date_for_ad_data
from app.core.country_code import resolve_country_name
from app.core.query_utils import apply_date_range_filter, check_use_assignment_table
from app.core.security import is_admin
from app.models.models import AdData, Client, CountryInfo, Product, User
from app.services.ad_data.queries.filter_conditions import (
    InvalidFilterParameterError,
    apply_ad_data_scope_filters,
    validate_ad_data_scope_filter_params,
)
from app.services.ad_data.queries.dimension_filter import (
    build_daily_summary_dimension_filter,
    is_cross_dimension,
    normalize_dimension,
)
from app.services.ad_data.queries.join_helpers import join_country_info_for_ad_data, join_product_and_client
from app.services.ad_data.query_cache import (
    ad_data_daily_summary_cache_ttl,
    ad_data_get_or_set,
    build_ad_data_query_cache_key,
)
from app.services.ad_data.queries.summary_query import (
    _empty_aggregate_raw,
    _row_to_aggregate_raw,
    build_table_grand_total_payload,
)

logger = logging.getLogger(__name__)

def _effective_summary_date_range(
    start_date: Optional[date],
    end_date: Optional[date],
) -> Tuple[Optional[date], Optional[date]]:
    """与 apply_date_range_filter(default_to_current_month=True) 对齐的有效区间。"""
    if start_date or end_date:
        return start_date, end_date
    today = date.today()
    _, last_day = monthrange(today.year, today.month)
    return date(today.year, today.month, 1), date(today.year, today.month, last_day)


def _daily_summary_dimension_filter(
    dimension: str,
    start_date: Optional[date],
    end_date: Optional[date],
):
    return build_daily_summary_dimension_filter(
        AdData.country_code,
        AdData.ad_unit,
        dimension,
        start_date=start_date,
        end_date=end_date,
    )


def _daily_summary_aggregate_columns():
    """与 summary_query 一致的明细级 SUM 聚合（用于全量合计行）。"""
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


class DailySummaryQuery:
    """按统计维度分组的每日汇总查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 10,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        client_id: Optional[str | int] = None,
        product_id: Optional[str] = None,
        country_code: Optional[str] = None,
        ad_unit: Optional[str] = None,
        dimension: Optional[str] = None,
        split_by_country: bool = False,
        sort_by: str = "date",
        sort_order: str = "desc",
        skip_cache: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int, Dict[str, Any]]:
        """
        获取按统计维度分组的每日汇总列表（分页）。

        Returns:
            (汇总行字典列表, 分组总数, 全量合计指标)
        """
        dim = normalize_dimension(dimension)
        dim_start, dim_end = _effective_summary_date_range(start_date, end_date)

        validate_ad_data_scope_filter_params(
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
        )

        cache_key = build_ad_data_query_cache_key(
            "daily_summary",
            current_user.id,
            page,
            page_size,
            start_date,
            end_date,
            client_id,
            product_id,
            country_code,
            ad_unit,
            dim,
            bool(split_by_country),
            sort_by,
            sort_order,
        )

        async def _produce_payload() -> Dict[str, Any]:
            items, total, grand_total = await self._fetch_uncached(
                current_user=current_user,
                page=page,
                page_size=page_size,
                start_date=start_date,
                end_date=end_date,
                client_id=client_id,
                product_id=product_id,
                country_code=country_code,
                ad_unit=ad_unit,
                dim=dim,
                dim_start=dim_start,
                dim_end=dim_end,
                split_by_country=split_by_country,
                sort_by=sort_by,
                sort_order=sort_order,
                skip_cache=skip_cache,
            )
            return {
                "items": items,
                "total": total,
                "grand_total": grand_total,
            }

        def _payload_valid(cached: Any) -> bool:
            return (
                isinstance(cached, dict)
                and "items" in cached
                and "total" in cached
                and "grand_total" in cached
            )

        if skip_cache:
            payload = await _produce_payload()
        else:
            payload = await ad_data_get_or_set(
                cache_key,
                _produce_payload,
                ttl=ad_data_daily_summary_cache_ttl(),
                is_valid=_payload_valid,
            )
        return (
            payload["items"],
            int(payload.get("total") or 0),
            payload["grand_total"],
        )

    async def _fetch_uncached(
        self,
        *,
        current_user: User,
        page: int,
        page_size: int,
        start_date: Optional[date],
        end_date: Optional[date],
        client_id: Optional[str | int],
        product_id: Optional[str],
        country_code: Optional[str],
        ad_unit: Optional[str],
        dim: str,
        dim_start: Optional[date],
        dim_end: Optional[date],
        split_by_country: bool,
        sort_by: str,
        sort_order: str,
        skip_cache: bool,
    ) -> Tuple[List[Dict[str, Any]], int, Dict[str, Any]]:
        """每日汇总冷路径（无外层列表缓存；合计子缓存仍可命中）。"""
        use_assignment_table = await check_use_assignment_table(self.db)
        group_by_ad_unit = dim == "ad_unit" or is_cross_dimension(dim)
        group_by_country = split_by_country or is_cross_dimension(dim)

        grand_cache_key = build_ad_data_query_cache_key(
            "daily_summary_grand",
            current_user.id,
            start_date,
            end_date,
            client_id,
            product_id,
            country_code,
            ad_unit,
            dim,
        )

        async def _load_grand_total() -> Dict[str, Any]:
            async def _compute_grand() -> Dict[str, Any]:
                async with AsyncSessionLocal() as session:
                    gt = await DailySummaryQuery(session).fetch_grand_totals(
                        current_user=current_user,
                        start_date=start_date,
                        end_date=end_date,
                        client_id=client_id,
                        product_id=product_id,
                        country_code=country_code,
                        ad_unit=ad_unit,
                        dimension=dim,
                        use_assignment_table=use_assignment_table,
                    )
                return {"grand_total": gt}

            if skip_cache:
                return (await _compute_grand())["grand_total"]

            wrapped = await ad_data_get_or_set(
                grand_cache_key,
                _compute_grand,
                ttl=ad_data_daily_summary_cache_ttl(),
                is_valid=lambda c: isinstance(c, dict) and "grand_total" in c,
            )
            return wrapped["grand_total"]

        # 全量合计走独立会话，与列表/计数并行，缩短冷路径墙钟时间
        grand_task = asyncio.create_task(_load_grand_total())

        metric_columns = [
            func.sum(AdData.request_count).label("request_count"),
            func.sum(AdData.match_count).label("match_count"),
            func.sum(AdData.display_count).label("display_count"),
            func.sum(AdData.click_count).label("click_count"),
            func.avg(AdData.viewability_rate).label("viewability_rate"),
            func.sum(AdData.pageviews).label("pageviews"),
            func.sum(AdData.revenue_after_deduct).label("revenue_after_deduct"),
            func.sum(AdData.revenue_before_deduct).label("revenue_before_deduct"),
        ]

        base_dims = [
            AdData.date.label("date"),
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Client.id.label("client_id"),
            Client.company_name.label("client_name"),
            User.full_name.label("user_full_name"),
            User.username.label("user_username"),
        ]

        group_by_cols: List[Any] = [
            AdData.date,
            Product.id,
            Product.name,
            Client.id,
            Client.company_name,
            User.full_name,
            User.username,
        ]

        select_cols = list(base_dims)
        if group_by_ad_unit:
            select_cols.append(AdData.ad_unit.label("ad_unit"))
            group_by_cols.append(AdData.ad_unit)
        if group_by_country:
            select_cols.append(AdData.country_code.label("country_code"))
            select_cols.append(func.max(CountryInfo.country_name_zh).label("country_name_zh"))
            group_by_cols.append(AdData.country_code)

        query = select(*select_cols, *metric_columns)
        query = join_product_and_client(query, use_assignment_table)
        if group_by_country:
            query = join_country_info_for_ad_data(query)

        query = query.where(Product.is_active == True)
        query = query.join(User, Client.user_id == User.id)
        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True,
        )
        query = query.where(_daily_summary_dimension_filter(dim, dim_start, dim_end))
        query = await apply_ad_data_scope_filters(
            self.db,
            query,
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            dimension=dim,
        )

        query = query.group_by(*group_by_cols)

        valid_sort_fields = {
            "date": AdData.date,
            "product": Product.name,
            "ad_unit": AdData.ad_unit if group_by_ad_unit else None,
            "country": AdData.country_code if group_by_country else None,
            "product_id": Product.id,
            "request_count": func.sum(AdData.request_count),
            "match_count": func.sum(AdData.match_count),
            "display_count": func.sum(AdData.display_count),
            "click_count": func.sum(AdData.click_count),
            "pageviews": func.sum(AdData.pageviews),
            "coverage_rate": func.avg(AdData.coverage_rate),
            "display_rate": func.avg(AdData.display_rate),
            "click_rate": func.avg(AdData.click_rate),
            "viewability_rate": func.avg(AdData.viewability_rate),
            "ecpm_after_deduct": func.sum(AdData.revenue_after_deduct),
            "revenue_after_deduct": func.sum(AdData.revenue_after_deduct),
            "revenue_before_deduct": func.sum(AdData.revenue_before_deduct),
        }
        valid_sort_fields = {k: v for k, v in valid_sort_fields.items() if v is not None}

        memory_sort_fields = {"ecpm_before_deduct"}
        need_memory_sort = sort_by in memory_sort_fields

        # 稳定排序：主排序键 + 全部分组维度，避免 OFFSET 跨页漏/重
        tie_breakers: List[Any] = [AdData.date.asc(), Product.id.asc()]
        if group_by_ad_unit:
            tie_breakers.append(AdData.ad_unit.asc())
        if group_by_country:
            tie_breakers.append(AdData.country_code.asc())

        if sort_by in valid_sort_fields:
            sort_column = valid_sort_fields[sort_by]
            primary = sort_column.desc() if sort_order.lower() == "desc" else sort_column.asc()
            query = query.order_by(primary, *tie_breakers)
        elif not need_memory_sort:
            sort_by = "date"
            sort_column = valid_sort_fields[sort_by]
            primary = sort_column.desc() if sort_order.lower() == "desc" else sort_column.asc()
            query = query.order_by(primary, *tie_breakers)

        # SQL 分页路径：窗口计数与列表同一次聚合，省掉独立 _count_groups 全表重扫
        if not need_memory_sort:
            query = query.add_columns(func.count().over().label("_group_total"))

        total = 0
        if need_memory_sort:
            result = await self.db.execute(query)
            all_summary_data = result.all()
        else:
            offset = (page - 1) * page_size
            result = await self.db.execute(query.offset(offset).limit(page_size))
            all_summary_data = result.all()
            if all_summary_data:
                total = int(getattr(all_summary_data[0], "_group_total", 0) or 0)
            else:
                # 空页（无数据或 OFFSET 越界）仍需准确总数
                total = await self._count_groups(
                    use_assignment_table,
                    current_user,
                    client_id,
                    product_id,
                    country_code,
                    ad_unit,
                    dim,
                    dim_start,
                    dim_end,
                    start_date,
                    end_date,
                    group_by_ad_unit,
                    group_by_country,
                )

        ad_data_responses = []
        for row in all_summary_data:
            date_obj = normalize_date_for_ad_data(row.date)
            date_str = date_obj.isoformat() if hasattr(date_obj, "isoformat") else str(date_obj)

            total_request_count = int(row.request_count or 0)
            total_match_count = int(row.match_count or 0)
            total_display_count = int(row.display_count or 0)
            total_click_count = int(row.click_count or 0)
            total_viewability_rate = float(row.viewability_rate or 0.0)
            total_pageviews = int(row.pageviews or 0)
            total_revenue_after = float(row.revenue_after_deduct or 0.0)
            total_revenue_before = float(row.revenue_before_deduct or 0.0)

            coverage_rate = round(
                (total_match_count / total_request_count * PERCENTAGE_MULTIPLIER)
                if total_request_count > 0
                else 0.0,
                2,
            )
            display_rate = round(
                (total_display_count / total_match_count * PERCENTAGE_MULTIPLIER)
                if total_match_count > 0
                else 0.0,
                2,
            )
            click_rate = round(
                (total_click_count / total_display_count * 100) if total_display_count > 0 else 0.0,
                2,
            )
            total_cpc = round(
                (total_revenue_after / total_click_count) if total_click_count > 0 else 0.0,
                2,
            )
            ecpm_after_deduct = round(
                (total_revenue_after / total_display_count * ECPM_MULTIPLIER)
                if total_display_count > 0
                else 0.0,
                4,
            )
            ecpm_before_deduct = round(
                (total_revenue_before / total_display_count * ECPM_MULTIPLIER)
                if total_display_count > 0
                else 0.0,
                4,
            )

            client_name = row.client_name or ""
            user_name = row.user_full_name or row.user_username or ""

            row_ad_unit = getattr(row, "ad_unit", "") if group_by_ad_unit else ""

            if group_by_country:
                row_country_code = getattr(row, "country_code", "") or ""
                row_country_name = getattr(row, "country_name_zh", None)
                display_country_code = row_country_code
                country_name_zh = row_country_name or resolve_country_name(
                    None, row_country_code
                )
            else:
                display_country_code = "ZZ"
                country_name_zh = "全部区域"

            response_data = {
                "id": 0,
                "date": date_str,
                "product_id": row.product_id,
                "product_name": row.product_name or "",
                "ad_unit": row_ad_unit or "",
                "country_code": display_country_code,
                "country_name_zh": country_name_zh,
                "request_count": total_request_count,
                "match_count": total_match_count,
                "coverage_rate": coverage_rate,
                "display_count": total_display_count,
                "display_rate": display_rate,
                "click_count": total_click_count,
                "click_rate": click_rate,
                "viewability_rate": round(total_viewability_rate, 2),
                "cpc": total_cpc,
                "pageviews": total_pageviews,
                "ecpm_after_deduct": ecpm_after_deduct,
                "revenue_after_deduct": round(total_revenue_after, 4),
                "user_name": user_name,
            }

            if is_admin(current_user):
                response_data.update(
                    {
                        "client_id": row.client_id,
                        "client_name": client_name,
                        "ecpm_before_deduct": ecpm_before_deduct,
                        "revenue_before_deduct": round(total_revenue_before, 4),
                    }
                )

            ad_data_responses.append(response_data)

        if need_memory_sort:
            reverse_order = sort_order.lower() == "desc"
            if sort_by == "ecpm_before_deduct":
                # 主排序 + 分组维度稳定键，避免同 eCPM 时切片漏/重
                ad_data_responses.sort(
                    key=lambda x: (
                        x.get("ecpm_before_deduct", 0) or 0,
                        str(x.get("date") or ""),
                        int(x.get("product_id") or 0),
                        str(x.get("ad_unit") or ""),
                        str(x.get("country_code") or ""),
                    ),
                    reverse=reverse_order,
                )
            total = len(ad_data_responses)
            offset = (page - 1) * page_size
            ad_data_responses = ad_data_responses[offset : offset + page_size]

        try:
            grand_total = await grand_task
        except Exception:
            # 合计失败不应丢掉已算好的列表；回退空合计并记录
            if not grand_task.done():
                grand_task.cancel()
            logger.exception("daily-summary 全量合计并行查询失败，回退空合计")
            grand_total = build_table_grand_total_payload(
                raw=_empty_aggregate_raw(),
                for_admin=is_admin(current_user),
            )

        return ad_data_responses, total, grand_total

    async def fetch_grand_totals(
        self,
        current_user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        client_id: Optional[str | int] = None,
        product_id: Optional[str] = None,
        country_code: Optional[str] = None,
        ad_unit: Optional[str] = None,
        dimension: Optional[str] = None,
        use_assignment_table: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """当前筛选条件下全部明细的全量合计（供表格底部合计行，不受分页影响）。"""
        dim = normalize_dimension(dimension)
        dim_start, dim_end = _effective_summary_date_range(start_date, end_date)
        if use_assignment_table is None:
            use_assignment_table = await check_use_assignment_table(self.db)
        admin_user = is_admin(current_user)
        validate_ad_data_scope_filter_params(
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
        )

        query = select(*_daily_summary_aggregate_columns())
        query = join_product_and_client(query, use_assignment_table)
        query = query.where(Product.is_active == True)
        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True,
        )
        query = query.where(_daily_summary_dimension_filter(dim, dim_start, dim_end))
        query = await apply_ad_data_scope_filters(
            self.db,
            query,
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            dimension=dim,
        )

        row = (await self.db.execute(query)).first()
        raw = _row_to_aggregate_raw(row) if row else _empty_aggregate_raw()
        return build_table_grand_total_payload(raw=raw, for_admin=admin_user)

    async def _count_groups(
        self,
        use_assignment_table: bool,
        current_user: User,
        client_id: Optional[str | int],
        product_id: Optional[str],
        country_code: Optional[str],
        ad_unit: Optional[str],
        dimension: str,
        dim_start: Optional[date],
        dim_end: Optional[date],
        start_date: Optional[date],
        end_date: Optional[date],
        group_by_ad_unit: bool,
        group_by_country: bool,
    ) -> int:
        try:
            sub_cols = [
                AdData.date.label("date"),
                Product.id.label("product_id"),
                Client.id.label("client_id"),
            ]
            group_cols = [AdData.date, Product.id, Client.id]

            if group_by_ad_unit:
                sub_cols.append(AdData.ad_unit.label("ad_unit"))
                group_cols.append(AdData.ad_unit)
            if group_by_country:
                sub_cols.append(AdData.country_code.label("country_code"))
                group_cols.append(AdData.country_code)

            subquery = select(*sub_cols)
            subquery = join_product_and_client(subquery, use_assignment_table)
            subquery = subquery.where(Product.is_active == True)
            subquery = apply_date_range_filter(
                subquery,
                AdData.date,
                start_date,
                end_date,
                default_to_current_month=True,
            )
            subquery = subquery.where(
                _daily_summary_dimension_filter(dimension, dim_start, dim_end)
            )
            subquery = await apply_ad_data_scope_filters(
                self.db,
                subquery,
                current_user=current_user,
                client_id=client_id,
                product_id=product_id,
                country_code=country_code,
                ad_unit=ad_unit,
                dimension=dimension,
            )

            subquery = subquery.group_by(*group_cols)

            count_query = select(func.count()).select_from(subquery.alias("distinct_groups"))
            count_result = await self.db.execute(count_query)
            return count_result.scalar() or 0
        except InvalidFilterParameterError:
            raise
        except Exception as e:
            logger.error("计算每日汇总总数失败: %s", str(e))
            return 0
