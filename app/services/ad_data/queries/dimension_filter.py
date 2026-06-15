"""
广告数据统计维度筛选条件。

三种互斥维度，避免国家 API 与广告单元 API 数据重复展示：
- country：按国家（ad_unit 为空，国家非 AA/ZZ）
- ad_unit：按广告单元（国家为 AA/ZZ/空，ad_unit 有值）
- country_ad_unit：按国家+广告单元（两者均有有效值）
"""
from typing import Any, Optional, Set

from sqlalchemy import and_, or_

VALID_DIMENSIONS: Set[str] = frozenset({"country", "ad_unit", "country_ad_unit"})
DEFAULT_DIMENSION = "country"


def normalize_dimension(dimension: Optional[str]) -> str:
    """规范化统计维度参数，非法或空值回退为默认「按国家」。"""
    if dimension and str(dimension).strip() in VALID_DIMENSIONS:
        return str(dimension).strip()
    return DEFAULT_DIMENSION


def _empty_ad_unit_condition(ad_unit_column: Any) -> Any:
    return or_(ad_unit_column.is_(None), ad_unit_column == "")


def _non_empty_ad_unit_condition(ad_unit_column: Any) -> Any:
    return and_(ad_unit_column.isnot(None), ad_unit_column != "")


def _no_country_breakdown_condition(country_code_column: Any) -> Any:
    """广告单元维度：国家为全部区域/未知/空。"""
    return or_(
        country_code_column.is_(None),
        country_code_column == "",
        country_code_column == "ZZ",
        country_code_column == "AA",
    )


def _valid_country_breakdown_condition(country_code_column: Any) -> Any:
    """有效国家拆分：排除 AA、ZZ 及空值。"""
    return and_(
        country_code_column.isnot(None),
        country_code_column != "",
        country_code_column != "ZZ",
        country_code_column != "AA",
    )


def build_ad_data_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dimension: Optional[str],
) -> Any:
    """构建统计维度 SQLAlchemy 筛选条件。"""
    dim = normalize_dimension(dimension)
    if dim == "country":
        return and_(
            _valid_country_breakdown_condition(country_code_column),
            _empty_ad_unit_condition(ad_unit_column),
        )
    if dim == "ad_unit":
        return and_(
            _no_country_breakdown_condition(country_code_column),
            _non_empty_ad_unit_condition(ad_unit_column),
        )
    return and_(
        _valid_country_breakdown_condition(country_code_column),
        _non_empty_ad_unit_condition(ad_unit_column),
    )


def build_ad_unit_exact_filter(ad_unit_column: Any, ad_unit_input: Optional[str]) -> Any | None:
    """按广告单元精确筛选；空输入表示不过滤。"""
    if not ad_unit_input or not str(ad_unit_input).strip():
        return None
    return ad_unit_column == str(ad_unit_input).strip()
