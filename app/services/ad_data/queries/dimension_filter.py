"""
广告数据统计维度筛选条件。

明细列表（互斥字段，避免多 API 重复展示）：
- country：按国家（ad_unit 为空，有国家代码，含 AA/ZZ）
- ad_unit：按广告单元（无国家代码即 NULL/空串，ad_unit 有值）
- ad_unit_country：按广告单元+国家（有国家代码含 AA/ZZ，ad_unit 有值）

每日汇总使用 build_daily_summary_dimension_filter（放宽互斥约束，见该函数说明）。
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


def _no_country_condition(country_code_column: Any) -> Any:
    """无国家：country_code 为 NULL 或空串。"""
    return or_(
        country_code_column.is_(None),
        country_code_column == "",
    )


def _has_country_condition(country_code_column: Any) -> Any:
    """有国家：country_code 非空（含 AA、ZZ 等特殊代码）。"""
    return and_(
        country_code_column.isnot(None),
        country_code_column != "",
    )


def row_has_country(country_code: Optional[str]) -> bool:
    """行级判断：是否有国家代码（含 AA、ZZ）。"""
    return bool((country_code or "").strip())


def row_has_no_country(country_code: Optional[str]) -> bool:
    """行级判断：是否无国家代码。"""
    return not row_has_country(country_code)


def build_ad_data_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dimension: Optional[str],
) -> Any:
    """构建明细列表用统计维度筛选（互斥字段，避免多 API 重复计数）。"""
    dim = normalize_dimension(dimension)
    if dim == "country":
        return and_(
            _has_country_condition(country_code_column),
            _empty_ad_unit_condition(ad_unit_column),
        )
    if dim == "ad_unit":
        return and_(
            _no_country_condition(country_code_column),
            _non_empty_ad_unit_condition(ad_unit_column),
        )
    return and_(
        _has_country_condition(country_code_column),
        _non_empty_ad_unit_condition(ad_unit_column),
    )


def build_daily_summary_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dimension: Optional[str],
) -> Any:
    """
    构建每日汇总用统计维度筛选（放宽互斥约束）。

    部分上游（如 Addermobi）单行同时含国家与广告单元，入库为交叉明细；
    每日汇总按日期+产品（及可选广告单元）聚合，不按国家分行，故：
    - 按国家：有国家代码即可（含交叉行），再汇总所有国家/广告单元
    - 按广告单元：有广告单元即可（含交叉行），按广告单元分组
    - 按广告单元+国家：与明细一致，要求同时有国家与广告单元
    """
    dim = normalize_dimension(dimension)
    if dim == "country":
        return _has_country_condition(country_code_column)
    if dim == "ad_unit":
        return _non_empty_ad_unit_condition(ad_unit_column)
    return and_(
        _has_country_condition(country_code_column),
        _non_empty_ad_unit_condition(ad_unit_column),
    )


def build_ad_unit_exact_filter(ad_unit_column: Any, ad_unit_input: Optional[str]) -> Any | None:
    """按广告单元精确筛选；空输入表示不过滤。"""
    if not ad_unit_input or not str(ad_unit_input).strip():
        return None
    return ad_unit_column == str(ad_unit_input).strip()


def country_exact_filter_applies(dimension: Optional[str]) -> bool:
    """按广告单元维度时国家字段恒为空，国家精确筛选不适用。"""
    return normalize_dimension(dimension) != "ad_unit"


def ad_unit_exact_filter_applies(dimension: Optional[str]) -> bool:
    """按国家维度时无广告单元数据，广告单元精确筛选不适用。"""
    return normalize_dimension(dimension) != "country"
