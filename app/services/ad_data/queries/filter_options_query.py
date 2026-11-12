"""
广告数据筛选器下拉选项查询。

功能说明：
- 客户 / 国家 / 产品 / 日期范围等有数据的可选项
- 供前端级联筛选器使用，部分结果带 Redis 缓存

在系统中的位置：
- 被 ``AdDataService`` 筛选器接口调用
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.db_errors import run_with_mysql_schema_retry
from app.core.country_code import resolve_country_name
from app.core.query_utils import apply_date_range_filter, check_use_assignment_table
from app.core.security import is_admin
from app.models.models import AdData, Client, CountryInfo, Product, User
from app.services.ad_data.queries.filter_conditions import (
    apply_ad_data_scope_filters,
    apply_client_ids_filter,
    parse_csv_ints,
)
from app.services.ad_data.queries.daily_summary_query import _effective_summary_date_range
from app.services.ad_data.queries.dimension_filter import (
    build_daily_summary_dimension_filter,
    is_all_list_dimension,
    normalize_dimension,
)
from app.services.ad_data.queries.join_helpers import (
    build_products_with_data_base_query,
    join_ad_data_and_client_from_product,
    join_country_info_for_ad_data,
    join_product_and_client,
    merge_product_options_with_ownership,
)
from app.services.ad_data.query_cache import (
    ad_data_filter_options_cache_ttl,
    ad_data_get_or_set,
    build_ad_data_query_cache_key,
)
logger = logging.getLogger(__name__)


def _filter_dropdown_dimension_filter(
    dimension: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """
    筛选项下拉与日汇总列表使用相同维度语义。

    GAM 等仅交叉入库时，「国家数据」页的国家下拉需包含交叉行中的国家，
    不可使用明细列表的互斥维度过滤（否则会始终为空、无法级联）。
    """
    eff_start, eff_end = _effective_summary_date_range(start_date, end_date)
    if is_all_list_dimension(dimension):
        from sqlalchemy import true

        return true()
    return build_daily_summary_dimension_filter(
        AdData.country_code,
        AdData.ad_unit,
        dimension,
        start_date=eff_start,
        end_date=eff_end,
    )


class FilterOptionsQuery:
    """广告数据筛选器下拉数据源查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_clients(
        self,
        current_user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        cache_key = build_ad_data_query_cache_key(
            "clients_with_data", current_user.id, start_date, end_date
        )

        async def _load_payload() -> Dict[str, Any]:
            async def _load() -> List[Dict[str, Any]]:
                use_assignment_table = await check_use_assignment_table(self.db)

                if use_assignment_table:
                    query = select(func.distinct(Client.id), User.full_name, User.username, Client.user_id)
                    query = query.select_from(AdData)
                    query = join_product_and_client(query, use_assignment_table)
                else:
                    query = select(func.distinct(Client.id), User.full_name, User.username, Client.user_id)
                    query = query.select_from(Client)
                    query = query.join(Product, Product.client_id == Client.id)
                    query = query.join(AdData, AdData.product_id == Product.id)

                query = query.join(User, Client.user_id == User.id)
                query = query.where(Product.is_active == True)

                if not is_admin(current_user):
                    query = query.where(Client.user_id == current_user.id, Client.is_active.is_(True))

                query = apply_date_range_filter(
                    query, AdData.date, start_date, end_date, default_to_current_month=True
                )

                result = await self.db.execute(query)
                clients = [
                    {
                        "id": client_id,
                        "full_name": full_name or username or "未知客户",
                        "user_id": user_id,
                    }
                    for client_id, full_name, username, user_id in result.all()
                ]
                clients.sort(key=lambda x: x["full_name"])
                return clients

            clients_list = await run_with_mysql_schema_retry(
                self.db, _load, label="clients_with_data"
            )
            return {"data": clients_list, "count": len(clients_list)}

        payload = await ad_data_get_or_set(
            cache_key,
            _load_payload,
            ttl=ad_data_filter_options_cache_ttl(),
            is_valid=lambda c: isinstance(c, dict) and "data" in c,
        )
        return payload.get("data") or []

    async def fetch_countries(
        self,
        current_user: User,
        client_id: Optional[str | int] = None,
        product_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        dimension: Optional[str] = None,
        ad_unit: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        dim = normalize_dimension(dimension)
        if dim == "ad_unit":
            return []

        cache_key = build_ad_data_query_cache_key(
            "countries_with_data",
            current_user.id,
            client_id,
            product_id,
            start_date,
            end_date,
            dim,
            ad_unit,
        )

        async def _load_payload() -> Dict[str, Any]:
            use_assignment_table = await check_use_assignment_table(self.db)

            query = select(func.distinct(AdData.country_code), CountryInfo.country_name_zh).select_from(AdData)
            query = join_product_and_client(query, use_assignment_table)
            query = join_country_info_for_ad_data(query)
            query = query.where(Product.is_active == True)
            query = query.where(_filter_dropdown_dimension_filter(dim, start_date, end_date))
            query = await apply_ad_data_scope_filters(
                self.db,
                query,
                current_user=current_user,
                client_id=client_id,
                product_id=product_id,
                country_code=None,
                ad_unit=ad_unit,
                dimension=dim,
            )

            query = apply_date_range_filter(
                query, AdData.date, start_date, end_date, default_to_current_month=True
            )
            query = query.where(and_(AdData.country_code.isnot(None), AdData.country_code != ""))

            countries_list = []
            for country_code, country_name_zh in (await self.db.execute(query)).all():
                if not country_code:
                    continue
                display_name = (
                    country_name_zh
                    or resolve_country_name(
                        None,
                        country_code,
                        default_unknown="未知区域",
                        default_all="全部区域",
                    )
                    or country_code
                )
                countries_list.append({"code": country_code, "name_zh": display_name})

            countries_list.sort(key=lambda x: x["name_zh"])
            return {"data": countries_list, "count": len(countries_list)}

        payload = await ad_data_get_or_set(
            cache_key,
            _load_payload,
            ttl=ad_data_filter_options_cache_ttl(),
            is_valid=lambda c: isinstance(c, dict) and "data" in c,
        )
        return payload.get("data") or []

    async def fetch_ad_units(
        self,
        current_user: User,
        client_id: Optional[str | int] = None,
        product_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        dimension: Optional[str] = None,
        country_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        dim = normalize_dimension(dimension)
        if dim == "country":
            return []

        cache_key = build_ad_data_query_cache_key(
            "ad_units_with_data",
            current_user.id,
            client_id,
            product_id,
            start_date,
            end_date,
            dim,
            country_code,
        )

        async def _load_payload() -> Dict[str, Any]:
            use_assignment_table = await check_use_assignment_table(self.db)

            query = select(func.distinct(AdData.ad_unit)).select_from(AdData)
            query = join_product_and_client(query, use_assignment_table)
            query = query.where(Product.is_active == True)
            query = query.where(_filter_dropdown_dimension_filter(dim, start_date, end_date))
            query = query.where(and_(AdData.ad_unit.isnot(None), AdData.ad_unit != ""))
            query = await apply_ad_data_scope_filters(
                self.db,
                query,
                current_user=current_user,
                client_id=client_id,
                product_id=product_id,
                country_code=country_code,
                ad_unit=None,
                dimension=dim,
            )

            query = apply_date_range_filter(
                query, AdData.date, start_date, end_date, default_to_current_month=True
            )

            ad_units_list = [
                {"value": unit, "label": unit}
                for (unit,) in (await self.db.execute(query)).all()
                if unit
            ]
            ad_units_list.sort(key=lambda x: x["label"])
            return {"data": ad_units_list, "count": len(ad_units_list)}

        payload = await ad_data_get_or_set(
            cache_key,
            _load_payload,
            ttl=ad_data_filter_options_cache_ttl(),
            is_valid=lambda c: isinstance(c, dict) and "data" in c,
        )
        return payload.get("data") or []

    async def fetch_products(
        self,
        current_user: User,
        client_id: Optional[str | int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        cache_key = build_ad_data_query_cache_key(
            "products_with_data",
            "assignment_and_current_v2",
            current_user.id,
            client_id,
            start_date,
            end_date,
        )

        async def _load_payload() -> Dict[str, Any]:
            use_assignment_table = await check_use_assignment_table(self.db)

            # 路径 1：分配历史 — 按每条广告数据的日期匹配当时归属客户（随日期范围动态变化）
            assignment_query = build_products_with_data_base_query()
            assignment_query = join_ad_data_and_client_from_product(
                assignment_query, use_assignment_table
            )
            if not is_admin(current_user):
                assignment_query = assignment_query.where(Client.user_id == current_user.id, Client.is_active.is_(True))
            else:
                client_filter = apply_client_ids_filter(
                    Client.id, parse_csv_ints(client_id, field="client_id")
                )
                if client_filter is not None:
                    assignment_query = assignment_query.where(client_filter)

            assignment_query = apply_date_range_filter(
                assignment_query,
                AdData.date,
                start_date,
                end_date,
                default_to_current_month=True,
            )
            assignment_rows = (await self.db.execute(assignment_query)).all()

            has_dual_path = use_assignment_table and not is_admin(current_user)
            current_rows = None
            if has_dual_path:
                current_query = build_products_with_data_base_query()
                current_query = current_query.join(AdData, AdData.product_id == Product.id)
                current_query = current_query.join(Client, Product.client_id == Client.id)
                current_query = current_query.where(Client.user_id == current_user.id, Client.is_active.is_(True))
                current_query = apply_date_range_filter(
                    current_query,
                    AdData.date,
                    start_date,
                    end_date,
                    default_to_current_month=True,
                )
                current_rows = (await self.db.execute(current_query)).all()

            scope_client_ids = None
            if use_assignment_table and is_admin(current_user):
                scope_client_ids = parse_csv_ints(client_id, field="client_id")

            products_list = merge_product_options_with_ownership(
                assignment_rows,
                current_rows,
                scope_client_ids=scope_client_ids,
                has_dual_path=has_dual_path,
            )
            products_list.sort(key=lambda x: x["id"], reverse=True)
            return {"data": products_list, "count": len(products_list)}

        payload = await ad_data_get_or_set(
            cache_key,
            _load_payload,
            ttl=ad_data_filter_options_cache_ttl(),
            is_valid=lambda c: isinstance(c, dict) and "data" in c,
        )
        return payload.get("data") or []

    async def fetch_date_range(
        self,
        current_user: User,
        client_id: Optional[str | int] = None,
    ) -> Dict[str, Optional[str]]:
        cache_key = build_ad_data_query_cache_key(
            "date_range",
            current_user.id,
            client_id,
        )

        async def _load_payload() -> Dict[str, Optional[str]]:
            # 管理员未指定客户时，日期范围只取有效产品对应的广告数据；
            # 分配历史只影响归属，不影响数据是否存在，避免为每条 ad_data 解析 assignment。
            if is_admin(current_user) and not client_id:
                query = (
                    select(func.min(AdData.date).label("min_date"), func.max(AdData.date).label("max_date"))
                    .select_from(AdData)
                    .join(Product, AdData.product_id == Product.id)
                    .where(Product.is_active == True)
                )
                row = (await self.db.execute(query)).first()
                return (
                    {
                        "min_date": row.min_date.isoformat() if row and row.min_date else None,
                        "max_date": row.max_date.isoformat() if row and row.max_date else None,
                    }
                    if row
                    else {"min_date": None, "max_date": None}
                )

            use_assignment_table = await check_use_assignment_table(self.db)

            query = select(
                func.min(AdData.date).label("min_date"),
                func.max(AdData.date).label("max_date"),
            ).select_from(AdData)
            query = join_product_and_client(query, use_assignment_table)

            query = query.where(Product.is_active == True)

            if not is_admin(current_user):
                query = query.where(Client.user_id == current_user.id, Client.is_active.is_(True))
            else:
                client_filter = apply_client_ids_filter(
                    Client.id, parse_csv_ints(client_id, field="client_id")
                )
                if client_filter is not None:
                    query = query.where(client_filter)

            row = (await self.db.execute(query)).first()
            if row and row.min_date and row.max_date:
                return {
                    "min_date": row.min_date.isoformat()
                    if hasattr(row.min_date, "isoformat")
                    else str(row.min_date),
                    "max_date": row.max_date.isoformat()
                    if hasattr(row.max_date, "isoformat")
                    else str(row.max_date),
                }
            return {"min_date": None, "max_date": None}

        return await ad_data_get_or_set(
            cache_key,
            _load_payload,
            ttl=ad_data_filter_options_cache_ttl(),
            is_valid=lambda c: isinstance(c, dict) and "min_date" in c and "max_date" in c,
        )
