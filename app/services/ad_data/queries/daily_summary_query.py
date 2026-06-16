"""
广告数据每日汇总查询构建器。

功能说明：
- 按统计维度分组聚合：按国家→日期+产品；按广告单元→日期+产品+广告单元；
  按广告单元+国家→日期+产品+广告单元（汇总所有国家，不按国家分行）
- 支持权限过滤、分页、SQL/内存混合排序

在系统中的位置：
- 被 ``AdDataService.get_daily_summary`` 调用
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import ECPM_MULTIPLIER, PERCENTAGE_MULTIPLIER
from app.core.country_code import build_ad_data_country_filter
from app.core.query_utils import apply_date_range_filter, check_use_assignment_table
from app.core.security import is_admin
from app.models.models import AdData, Client, Product, User
from app.services.ad_data.queries.dimension_filter import (
    build_ad_data_dimension_filter,
    build_ad_unit_exact_filter,
    is_cross_dimension,
    normalize_dimension,
)
from app.services.ad_data.queries.join_helpers import join_product_and_client

logger = logging.getLogger(__name__)


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
        client_id: Optional[int] = None,
        product_id: Optional[str] = None,
        country_code: Optional[str] = None,
        ad_unit: Optional[str] = None,
        dimension: Optional[str] = None,
        sort_by: str = "date",
        sort_order: str = "desc",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        获取按统计维度分组的每日汇总列表（分页）。

        Returns:
            (汇总行字典列表, 分组总数)
        """
        dim = normalize_dimension(dimension)
        use_assignment_table = await check_use_assignment_table(self.db)

        metric_columns = [
            func.sum(AdData.request_count).label("request_count"),
            func.sum(AdData.match_count).label("match_count"),
            func.sum(AdData.display_count).label("display_count"),
            func.sum(AdData.click_count).label("click_count"),
            func.avg(AdData.viewability_rate).label("viewability_rate"),
            func.sum(AdData.cpc).label("cpc"),
            func.sum(AdData.pageviews).label("pageviews"),
            func.sum(AdData.revenue_after_deduct).label("revenue_after_deduct"),
            func.sum(AdData.revenue_before_deduct).label("revenue_before_deduct"),
        ]

        base_dims = [
            func.date(AdData.date).label("date"),
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Client.id.label("client_id"),
            Client.company_name.label("client_name"),
            User.full_name.label("user_full_name"),
            User.username.label("user_username"),
        ]

        group_by_cols: List[Any] = [
            func.date(AdData.date),
            Product.id,
            Product.name,
            Client.id,
            Client.company_name,
            User.full_name,
            User.username,
        ]

        # 每日汇总不按国家分行；ad_unit_country 仅筛选交叉明细数据源，再按日期+产品+广告单元汇总。
        group_by_ad_unit = dim == "ad_unit" or is_cross_dimension(dim)

        select_cols = list(base_dims)
        if group_by_ad_unit:
            select_cols.append(AdData.ad_unit.label("ad_unit"))
            group_by_cols.append(AdData.ad_unit)

        query = select(*select_cols, *metric_columns)
        query = join_product_and_client(query, use_assignment_table)
        query = query.where(Product.is_active == True)
        query = query.join(User, Client.user_id == User.id)

        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        elif client_id:
            query = query.where(Client.id == client_id)

        if product_id and product_id.strip():
            try:
                query = query.where(AdData.product_id == int(product_id))
            except ValueError:
                logger.warning("无效的产品ID参数: %s", product_id)

        query = query.where(
            build_ad_data_dimension_filter(AdData.country_code, AdData.ad_unit, dim)
        )

        country_filter = await build_ad_data_country_filter(
            self.db, AdData.country_code, country_code
        )
        if country_filter is not None:
            query = query.where(country_filter)

        ad_unit_filter = build_ad_unit_exact_filter(AdData.ad_unit, ad_unit)
        if ad_unit_filter is not None:
            query = query.where(ad_unit_filter)

        query = apply_date_range_filter(
            query,
            AdData.date,
            start_date,
            end_date,
            default_to_current_month=True,
        )

        query = query.group_by(*group_by_cols)

        valid_sort_fields = {
            "date": func.date(AdData.date),
            "product": Product.name,
            "ad_unit": AdData.ad_unit if group_by_ad_unit else None,
            "country": None,
            "product_id": Product.id,
            "request_count": func.sum(AdData.request_count),
            "match_count": func.sum(AdData.match_count),
            "display_count": func.sum(AdData.display_count),
            "click_count": func.sum(AdData.click_count),
            "cpc": func.sum(AdData.cpc),
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

        if sort_by in valid_sort_fields:
            sort_column = valid_sort_fields[sort_by]
            if sort_order.lower() == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())
        elif not need_memory_sort:
            sort_by = "date"
            sort_column = valid_sort_fields[sort_by]
            if sort_order.lower() == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())

        total = 0
        if not need_memory_sort:
            total = await self._count_groups(
                use_assignment_table,
                current_user,
                client_id,
                product_id,
                country_code,
                ad_unit,
                dim,
                start_date,
                end_date,
                group_by_ad_unit,
            )

        if need_memory_sort:
            result = await self.db.execute(query)
            all_summary_data = result.all()
        else:
            offset = (page - 1) * page_size
            result = await self.db.execute(query.offset(offset).limit(page_size))
            all_summary_data = result.all()

        ad_data_responses = []
        for row in all_summary_data:
            date_obj = (
                row.date
                if isinstance(row.date, date)
                else row.date.date()
                if hasattr(row.date, "date")
                else row.date
            )
            date_str = date_obj.isoformat() if hasattr(date_obj, "isoformat") else str(date_obj)

            total_request_count = int(row.request_count or 0)
            total_match_count = int(row.match_count or 0)
            total_display_count = int(row.display_count or 0)
            total_click_count = int(row.click_count or 0)
            total_viewability_rate = float(row.viewability_rate or 0.0)
            total_cpc = float(row.cpc or 0.0)
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
                "cpc": round(total_cpc, 2),
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
                ad_data_responses.sort(
                    key=lambda x: x.get("ecpm_before_deduct", 0) or 0,
                    reverse=reverse_order,
                )
            total = len(ad_data_responses)
            offset = (page - 1) * page_size
            ad_data_responses = ad_data_responses[offset : offset + page_size]

        return ad_data_responses, total

    async def _count_groups(
        self,
        use_assignment_table: bool,
        current_user: User,
        client_id: Optional[int],
        product_id: Optional[str],
        country_code: Optional[str],
        ad_unit: Optional[str],
        dimension: str,
        start_date: Optional[date],
        end_date: Optional[date],
        group_by_ad_unit: bool,
    ) -> int:
        try:
            sub_cols = [
                func.date(AdData.date).label("date"),
                Product.id.label("product_id"),
                Client.id.label("client_id"),
            ]
            group_cols = [func.date(AdData.date), Product.id, Client.id]

            if group_by_ad_unit:
                sub_cols.append(AdData.ad_unit.label("ad_unit"))
                group_cols.append(AdData.ad_unit)

            subquery = select(*sub_cols)
            subquery = join_product_and_client(subquery, use_assignment_table)
            subquery = subquery.where(Product.is_active == True)

            if not is_admin(current_user):
                subquery = subquery.where(Client.user_id == current_user.id)
            elif client_id:
                subquery = subquery.where(Client.id == client_id)

            if product_id and product_id.strip():
                try:
                    subquery = subquery.where(AdData.product_id == int(product_id))
                except ValueError:
                    pass

            subquery = subquery.where(
                build_ad_data_dimension_filter(AdData.country_code, AdData.ad_unit, dimension)
            )

            country_filter = await build_ad_data_country_filter(
                self.db, AdData.country_code, country_code
            )
            if country_filter is not None:
                subquery = subquery.where(country_filter)

            ad_unit_filter = build_ad_unit_exact_filter(AdData.ad_unit, ad_unit)
            if ad_unit_filter is not None:
                subquery = subquery.where(ad_unit_filter)

            subquery = apply_date_range_filter(
                subquery,
                AdData.date,
                start_date,
                end_date,
                default_to_current_month=True,
            )

            subquery = subquery.group_by(*group_cols)

            count_query = select(func.count()).select_from(subquery.alias("distinct_groups"))
            count_result = await self.db.execute(count_query)
            return count_result.scalar() or 0
        except Exception as e:
            logger.error("计算每日汇总总数失败: %s", str(e))
            return 0
