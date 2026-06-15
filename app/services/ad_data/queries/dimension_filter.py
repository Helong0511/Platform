"""
广告数据统计维度筛选条件。

三种互斥维度，避免国家 API 与广告单元 API 数据重复展示：
- country：按国家（ad_unit 为空，国家非 AA/ZZ）
- ad_unit：按广告单元（国家为 AA/ZZ/空，ad_unit 有值）
- ad_unit_country：按广告单元+国家（两者均有有效值）
- country_ad_unit：已废弃别名，等价于 ad_unit_country
"""
from typing import Any, Optional, Set

from sqlalchemy import and_, or_

CROSS_DIMENSION = "ad_unit_country"
LEGACY_CROSS_DIMENSION = "country_ad_unit"
VALID_DIMENSIONS: Set[str] = frozenset({"country", "ad_unit", CROSS_DIMENSION})
INPUT_DIMENSIONS: Set[str] = VALID_DIMENSIONS | {LEGACY_CROSS_DIMENSION}
DEFAULT_DIMENSION = "country"


def normalize_dimension(dimension: Optional[str]) -> str:
    """规范化统计维度参数，非法或空值回退为默认「按国家」。"""
    if not dimension:
        return DEFAULT_DIMENSION
    stripped = str(dimension).strip()
    if stripped == LEGACY_CROSS_DIMENSION:
        return CROSS_DIMENSION
    if stripped in VALID_DIMENSIONS:
        return stripped
    return DEFAULT_DIMENSION


def is_cross_dimension(dimension: Optional[str]) -> bool:
    """是否为「按广告单元+国家」交叉维度。"""
    return normalize_dimension(dimension) == CROSS_DIMENSION


def parse_optional_dimension(dimension: Optional[str]) -> Optional[str]:
    """
    解析可选统计维度（客户 API 等兼容场景）。

    - 未传 / 空字符串：返回 None，表示不按维度筛选（保持旧行为）
    - 合法值：返回规范化后的维度
    - 非法值：返回 None，由调用方校验并报错
    """
    if dimension is None:
        return None
    stripped = str(dimension).strip()
    if not stripped:
        return None
    if stripped in INPUT_DIMENSIONS:
        return normalize_dimension(stripped)
    return None


def ensure_valid_optional_dimension(dimension: Optional[str]) -> Optional[str]:
    """解析可选 dimension；非法非空值抛出 ValueError。"""
    if dimension is None:
        return None
    stripped = str(dimension).strip()
    if not stripped:
        return None
    if stripped not in INPUT_DIMENSIONS:
        raise ValueError(
            f"无效的 dimension 参数: {stripped}，"
            f"可选值: country（按国家）、ad_unit（按广告单元）、"
            f"ad_unit_country（按广告单元+国家）；country_ad_unit 为兼容别名"
        )
    return normalize_dimension(stripped)


def maybe_build_ad_data_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dimension: Optional[str],
) -> Any | None:
    """未传 dimension 时返回 None；传入合法 dimension 时返回筛选条件。"""
    dim = parse_optional_dimension(dimension)
    if dim is None:
        return None
    return build_ad_data_dimension_filter(country_code_column, ad_unit_column, dim)


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
