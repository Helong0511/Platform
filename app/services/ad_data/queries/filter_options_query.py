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

from app.core.country_code import resolve_country_name
from app.core.infrastructure.cache_compat import (
    generate_cache_key,
    legacy_get_cached as get_cached,
    legacy_set_cached as set_cached,
)
from app.core.query_utils import apply_date_range_filter, check_use_assignment_table
from app.core.security import is_admin
from app.models.models import AdData, Client, CountryInfo, Product, ProductAssignment, User
from app.services.ad_data.queries.filter_conditions import (
    apply_ad_data_scope_filters,
    apply_client_ids_filter,
    parse_csv_ints,
)
from app.services.ad_data.queries.dimension_filter import (
    build_ad_data_dimension_filter,
    normalize_dimension,
)
from app.services.ad_data.queries.join_helpers import (
    join_ad_data_and_client_from_product,
    join_country_info_for_ad_data,
    join_product_and_client,
)
logger = logging.getLogger(__name__)


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
        cache_key = generate_cache_key("clients_with_data", current_user.id, start_date, end_date)
        cached = await get_cached(cache_key, key_prefix="ad_data")
        if cached:
            return cached.get("data", [])

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
            query = query.where(Client.user_id == current_user.id)

        query = apply_date_range_filter(
            query, AdData.date, start_date, end_date, default_to_current_month=True
        )

        result = await self.db.execute(query)
        clients_list = [
            {
                "id": client_id,
                "full_name": full_name or username or "未知客户",
                "user_id": user_id,
            }
            for client_id, full_name, username, user_id in result.all()
        ]
        clients_list.sort(key=lambda x: x["full_name"])

        await set_cached(
            cache_key,
            {"data": clients_list, "count": len(clients_list)},
            ttl=300,
            key_prefix="ad_data",
        )
        return clients_list

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

        use_assignment_table = await check_use_assignment_table(self.db)

        query = select(func.distinct(AdData.country_code), CountryInfo.country_name_zh).select_from(AdData)
        query = join_product_and_client(query, use_assignment_table)
        query = join_country_info_for_ad_data(query)
        query = query.where(Product.is_active == True)
        query = query.where(
            build_ad_data_dimension_filter(AdData.country_code, AdData.ad_unit, dim)
        )
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
        return countries_list

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

        use_assignment_table = await check_use_assignment_table(self.db)

        query = select(func.distinct(AdData.ad_unit)).select_from(AdData)
        query = join_product_and_client(query, use_assignment_table)
        query = query.where(Product.is_active == True)
        query = query.where(
            build_ad_data_dimension_filter(AdData.country_code, AdData.ad_unit, dim)
        )
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
        return ad_units_list

    async def fetch_products(
        self,
        current_user: User,
        client_id: Optional[str | int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        cache_key = generate_cache_key(
            "products_with_data", current_user.id, client_id, start_date, end_date
        )
        cached = await get_cached(cache_key, key_prefix="ad_data")
        if cached:
            return cached.get("data", [])

        use_assignment_table = await check_use_assignment_table(self.db)

        query = select(func.distinct(Product.id), Product.name, Product.client_id)
        query = join_ad_data_and_client_from_product(query, use_assignment_table)

        query = query.where(Product.is_active == True)

        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        else:
            client_filter = apply_client_ids_filter(Client.id, parse_csv_ints(client_id))
            if client_filter is not None:
                query = query.where(client_filter)

        query = apply_date_range_filter(
            query, AdData.date, start_date, end_date, default_to_current_month=True
        )

        products_list = [
            {
                "id": product_id,
                "name": product_name or "未知产品",
                "client_id": product_client_id,
            }
            for product_id, product_name, product_client_id in (await self.db.execute(query)).all()
        ]
        products_list.sort(key=lambda x: x["id"], reverse=True)

        await set_cached(
            cache_key,
            {"data": products_list, "count": len(products_list)},
            ttl=300,
            key_prefix="ad_data",
        )
        return products_list

    async def fetch_date_range(
        self,
        current_user: User,
        client_id: Optional[str | int] = None,
    ) -> Dict[str, Optional[str]]:
        use_assignment_table = await check_use_assignment_table(self.db)

        query = select(
            func.min(func.date(AdData.date)).label("min_date"),
            func.max(func.date(AdData.date)).label("max_date"),
        ).select_from(AdData)
        query = join_product_and_client(query, use_assignment_table)

        query = query.where(Product.is_active == True)

        if not is_admin(current_user):
            query = query.where(Client.user_id == current_user.id)
        else:
            client_filter = apply_client_ids_filter(Client.id, parse_csv_ints(client_id))
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
