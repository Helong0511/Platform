"""
广告数据明细列表查询构建器。

功能说明：
- 构建广告明细分页列表的 SELECT/WHERE/JOIN/ORDER 条件
- 支持产品、客户、日期、国家等多维筛选与排序
- 返回 API 层可直接使用的字典列表

在系统中的位置：
- 被 ``AdDataService.get_ad_data`` 调用
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.ad_data_metadata import format_data_source_label, format_report_type_label
from app.core.country_code import resolve_country_name
from app.core.query_utils import (
    apply_date_range_filter,
    check_use_assignment_table,
)
from app.services.ad_data.queries.filter_conditions import (
    InvalidFilterParameterError,
    apply_ad_data_scope_filters,
    validate_ad_data_scope_filter_params,
)
from app.services.ad_data.queries.dimension_filter import build_ad_data_dimension_filter
from app.services.ad_data.queries.join_helpers import (
    CLIENT_LOAD_ONLY,
    join_country_info_for_ad_data,
    join_product_and_client,
)
from app.core.security import is_admin
from app.core.utils import (
    calculate_click_rate,
    calculate_coverage_rate,
    calculate_display_rate,
    unpack_ad_data_query_result,
)
from app.models.models import AdData, Client, CountryInfo, Product, ProductAssignment, User

logger = logging.getLogger(__name__)


class AdDataListQuery:
    """广告数据明细列表查询（含国家维度、权限与响应组装）。"""

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
        data_source: Optional[str] = None,
        upstream_account: Optional[str] = None,
        report_type: Optional[str] = None,
        sort_by: str = "date",
        sort_order: str = "desc",
    ) -> Tuple[List[Dict[str, Any]], int]:
        from app.api_v1.excel.utils import normalize_date_key

        use_assignment_table = await check_use_assignment_table(self.db)
        validate_ad_data_scope_filter_params(
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            data_source=data_source,
            upstream_account=upstream_account,
            report_type=report_type,
        )
        query = await self._build_main_query(
            use_assignment_table,
            current_user,
            client_id,
            product_id,
            country_code,
            ad_unit,
            dimension,
            start_date,
            end_date,
            data_source=data_source,
            upstream_account=upstream_account,
            report_type=report_type,
        )
        query = self._apply_sort(query, sort_by, sort_order)
        total = await self._count_total(
            use_assignment_table,
            current_user,
            client_id,
            product_id,
            country_code,
            ad_unit,
            dimension,
            start_date,
            end_date,
            data_source=data_source,
            upstream_account=upstream_account,
            report_type=report_type,
        )

        offset = (page - 1) * page_size
        result = await self.db.execute(query.offset(offset).limit(page_size))
        data = result.unique().all()

        return self._build_responses(data, use_assignment_table, current_user, normalize_date_key), total

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
        data_source: Optional[str] = None,
        upstream_account: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """当前筛选条件下全部明细的全量合计（供表格底部合计行，不受分页影响）。"""
        from app.services.ad_data.queries.daily_summary_query import _daily_summary_aggregate_columns
        from app.services.ad_data.queries.summary_query import (
            _empty_aggregate_raw,
            _row_to_aggregate_raw,
            build_table_grand_total_payload,
        )

        use_assignment_table = await check_use_assignment_table(self.db)
        admin_user = is_admin(current_user)
        validate_ad_data_scope_filter_params(
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            data_source=data_source,
            upstream_account=upstream_account,
            report_type=report_type,
        )

        query = select(*_daily_summary_aggregate_columns())
        query = join_product_and_client(query, use_assignment_table)
        query = query.where(Product.is_active == True)
        query = query.where(
            build_ad_data_dimension_filter(
                AdData.country_code, AdData.ad_unit, dimension,
                report_type_column=AdData.report_type,
            )
        )
        query = await apply_ad_data_scope_filters(
            self.db,
            query,
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            dimension=dimension,
            data_source=data_source,
            upstream_account=upstream_account,
            report_type=report_type,
        )

        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True,
        )

        row = (await self.db.execute(query)).first()
        raw = _row_to_aggregate_raw(row) if row else _empty_aggregate_raw()
        return build_table_grand_total_payload(raw=raw, for_admin=admin_user)

    async def _build_main_query(
        self,
        use_assignment_table: bool,
        current_user: User,
        client_id: Optional[str | int],
        product_id: Optional[str],
        country_code: Optional[str],
        ad_unit: Optional[str],
        dimension: Optional[str],
        start_date: Optional[date],
        end_date: Optional[date],
        data_source: Optional[str] = None,
        upstream_account: Optional[str] = None,
        report_type: Optional[str] = None,
    ):
        if use_assignment_table:
            query = select(AdData, Product, Client, User, ProductAssignment, CountryInfo)
        else:
            query = select(AdData, Product, Client, User, CountryInfo)

        query = query.options(CLIENT_LOAD_ONLY)
        query = join_product_and_client(query, use_assignment_table)
        query = query.join(User, Client.user_id == User.id)
        query = join_country_info_for_ad_data(query)
        query = query.where(Product.is_active == True)
        query = query.where(
            build_ad_data_dimension_filter(
                AdData.country_code, AdData.ad_unit, dimension,
                report_type_column=AdData.report_type,
            )
        )
        query = await apply_ad_data_scope_filters(
            self.db,
            query,
            current_user=current_user,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            dimension=dimension,
            data_source=data_source,
            upstream_account=upstream_account,
            report_type=report_type,
        )

        return apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True,
        )

    def _apply_sort(self, query, sort_by: str, sort_order: str):
        valid_sort_fields = {
            "date": AdData.date,
            "client": Client.company_name,
            "client_id": Client.id,
            "product": Product.name,
            "product_id": Product.id,
            "request_count": AdData.request_count,
            "match_count": AdData.match_count,
            "display_count": AdData.display_count,
            "click_count": AdData.click_count,
            "cpc": AdData.cpc,
            "pageviews": AdData.pageviews,
            "ecpm_after_deduct": AdData.ecpm_after_deduct,
            "ecpm_before_deduct": AdData.ecpm_before_deduct,
            "revenue_after_deduct": AdData.revenue_after_deduct,
            "revenue_before_deduct": AdData.revenue_before_deduct,
            "coverage_rate": AdData.coverage_rate,
            "display_rate": AdData.display_rate,
            "click_rate": AdData.click_rate,
            "viewability_rate": AdData.viewability_rate,
        }

        if sort_by not in valid_sort_fields:
            sort_by = "date"

        sort_column = valid_sort_fields[sort_by]
        if sort_order.lower() == "desc":
            return query.order_by(sort_column.desc())
        return query.order_by(sort_column.asc())

    async def _count_total(
        self,
        use_assignment_table: bool,
        current_user: User,
        client_id: Optional[str | int],
        product_id: Optional[str],
        country_code: Optional[str],
        ad_unit: Optional[str],
        dimension: Optional[str],
        start_date: Optional[date],
        end_date: Optional[date],
        data_source: Optional[str] = None,
        upstream_account: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> int:
        try:
            count_query = select(func.count(AdData.id))
            count_query = join_product_and_client(count_query, use_assignment_table)
            count_query = count_query.where(Product.is_active == True)
            count_query = count_query.where(
                build_ad_data_dimension_filter(
                AdData.country_code, AdData.ad_unit, dimension,
                report_type_column=AdData.report_type,
            )
            )
            count_query = await apply_ad_data_scope_filters(
                self.db,
                count_query,
                current_user=current_user,
                client_id=client_id,
                product_id=product_id,
                country_code=country_code,
                ad_unit=ad_unit,
                dimension=dimension,
                data_source=data_source,
                upstream_account=upstream_account,
                report_type=report_type,
            )
            count_query = apply_date_range_filter(
                count_query,
                AdData.date,
                start_date,
                end_date,
                default_to_current_month=True,
            )

            count_result = await self.db.execute(count_query)
            return count_result.scalar() or 0
        except InvalidFilterParameterError:
            raise
        except Exception as e:
            logger.error("计算广告数据总数失败: %s", str(e))
            return 0

    def _build_responses(self, data, use_assignment_table: bool, current_user: User, normalize_date_key):
        ad_data_responses = []
        for row in data:
            try:
                ad_data, product, client, user, _assignment, country_info = unpack_ad_data_query_result(
                    row, use_assignment_table
                )
            except (ValueError, Exception) as e:
                logger.warning("解构数据失败: %s, row=%s", str(e), row)
                continue

            coverage_rate = calculate_coverage_rate(
                ad_data.match_count, ad_data.request_count, ad_data.coverage_rate
            )
            display_rate = calculate_display_rate(
                ad_data.display_count, ad_data.match_count, ad_data.display_rate
            )
            click_rate = calculate_click_rate(
                ad_data.click_count, ad_data.display_count, ad_data.click_rate
            )
            viewability_rate = float(ad_data.viewability_rate) if ad_data.viewability_rate is not None else 0.0
            date_value = normalize_date_key(ad_data.date)
            country_name_zh = resolve_country_name(country_info, ad_data.country_code)

            response_data = {
                "id": ad_data.id,
                "date": date_value,
                "product_id": product.id,
                "product_name": product.name,
                "ad_unit": ad_data.ad_unit or "",
                "country_code": ad_data.country_code,
                "country_name_zh": country_name_zh,
                "request_count": ad_data.request_count,
                "match_count": ad_data.match_count,
                "coverage_rate": coverage_rate,
                "display_count": ad_data.display_count,
                "display_rate": display_rate,
                "click_count": ad_data.click_count,
                "click_rate": click_rate,
                "viewability_rate": round(viewability_rate, 2),
                "cpc": float(round(float(ad_data.cpc or 0), 2)),
                "pageviews": ad_data.pageviews or 0,
                "ecpm_after_deduct": float(round(float(ad_data.ecpm_after_deduct or 0), 4)),
                "revenue_after_deduct": float(round(float(ad_data.revenue_after_deduct or 0), 4)),
            }

            if is_admin(current_user):
                response_data.update(
                    {
                        "client_id": client.id,
                        "client_name": client.company_name,
                        "user_name": user.full_name or user.username,
                        "data_source": ad_data.data_source or "legacy",
                        "data_source_label": format_data_source_label(ad_data.data_source),
                        "upstream_account": ad_data.upstream_account or "",
                        "report_type": ad_data.report_type or "legacy",
                        "report_type_label": format_report_type_label(ad_data.report_type),
                        "is_deducted": bool(ad_data.is_deducted),
                        "ecpm_before_deduct": float(round(float(ad_data.ecpm_before_deduct or 0), 4)),
                        "revenue_before_deduct": float(round(float(ad_data.revenue_before_deduct or 0), 4)),
                    }
                )

            ad_data_responses.append(response_data)

        return ad_data_responses


# 兼容旧名称
ListQueryBuilder = AdDataListQuery
