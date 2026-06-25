"""
广告数据查询通用筛选条件（支持逗号分隔多选）。

前端传参示例：client_id=1,2&product_id=10,11&country_code=US,CN&ad_unit=a,b
单值传参保持兼容：client_id=1
"""
from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.country_code import build_ad_data_country_filter
from app.core.security import is_admin
from app.models.models import AdData, Client, User
from app.services.ad_data.queries.dimension_filter import (
    ad_unit_exact_filter_applies,
    country_exact_filter_applies,
    normalize_dimension,
)


class InvalidFilterParameterError(ValueError):
    """逗号分隔筛选参数格式无效（应返回友好校验错误，而非 500）。"""

    def __init__(self, field: str, invalid_part: str):
        self.field = field
        self.invalid_part = invalid_part
        super().__init__(f"筛选参数 {field} 格式无效：'{invalid_part}' 不是有效的整数")


def parse_csv_ints(
    value: Optional[str | int],
    *,
    field: str = "id",
) -> Optional[List[int]]:
    if value is None:
        return None
    if isinstance(value, int):
        return [value]
    text = str(value).strip()
    if not text:
        return None
    result: List[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            raise InvalidFilterParameterError(field, part) from None
    return result or None


def parse_csv_strs(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    result = [part.strip() for part in text.split(",") if part.strip()]
    return result or None


def apply_client_ids_filter(column: Any, client_ids: Optional[List[int]]) -> Any | None:
    if not client_ids:
        return None
    if len(client_ids) == 1:
        return column == client_ids[0]
    return column.in_(client_ids)


def apply_product_ids_filter(column: Any, product_ids: Optional[List[int]]) -> Any | None:
    if not product_ids:
        return None
    if len(product_ids) == 1:
        return column == product_ids[0]
    return column.in_(product_ids)


def build_ad_units_in_filter(column: Any, ad_units: Optional[List[str]]) -> Any | None:
    if not ad_units:
        return None
    cleaned = [unit.strip() for unit in ad_units if unit and str(unit).strip()]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return column == cleaned[0]
    return column.in_(cleaned)


async def build_country_codes_filter(
    db: AsyncSession,
    country_code_column: Any,
    country_codes: Optional[List[str]],
) -> Any | None:
    if not country_codes:
        return None
    conditions = []
    for code in country_codes:
        condition = await build_ad_data_country_filter(db, country_code_column, code)
        if condition is not None:
            conditions.append(condition)
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return or_(*conditions)


def validate_ad_data_scope_filter_params(
    *,
    current_user: User,
    client_id: Optional[str | int] = None,
    product_id: Optional[str] = None,
    country_code: Optional[str] = None,
    ad_unit: Optional[str] = None,
) -> None:
    """预先解析筛选参数；非法整数格式时抛出 InvalidFilterParameterError。"""
    if is_admin(current_user):
        parse_csv_ints(client_id, field="client_id")
    parse_csv_ints(product_id, field="product_id")
    parse_csv_strs(country_code)
    parse_csv_strs(ad_unit)


async def apply_ad_data_scope_filters(
    db: AsyncSession,
    query: Any,
    *,
    current_user: User,
    client_id: Optional[str | int] = None,
    product_id: Optional[str] = None,
    country_code: Optional[str] = None,
    ad_unit: Optional[str] = None,
    dimension: Optional[str] = None,
) -> Any:
    """应用客户/产品/国家/广告单元筛选（含多选）。"""
    validate_ad_data_scope_filter_params(
        current_user=current_user,
        client_id=client_id,
        product_id=product_id,
        country_code=country_code,
        ad_unit=ad_unit,
    )
    client_ids = parse_csv_ints(client_id, field="client_id")
    product_ids = parse_csv_ints(product_id, field="product_id")
    country_codes = parse_csv_strs(country_code)
    ad_units = parse_csv_strs(ad_unit)
    dim = normalize_dimension(dimension) if dimension else None

    if not is_admin(current_user):
        query = query.where(Client.user_id == current_user.id)
    else:
        client_filter = apply_client_ids_filter(Client.id, client_ids)
        if client_filter is not None:
            query = query.where(client_filter)

    product_filter = apply_product_ids_filter(AdData.product_id, product_ids)
    if product_filter is not None:
        query = query.where(product_filter)

    if dim and country_exact_filter_applies(dim):
        country_filter = await build_country_codes_filter(
            db, AdData.country_code, country_codes
        )
        if country_filter is not None:
            query = query.where(country_filter)

    if dim and ad_unit_exact_filter_applies(dim):
        ad_unit_filter = build_ad_units_in_filter(AdData.ad_unit, ad_units)
        if ad_unit_filter is not None:
            query = query.where(ad_unit_filter)

    return query
