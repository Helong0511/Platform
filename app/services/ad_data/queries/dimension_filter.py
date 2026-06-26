"""
广告数据统计维度筛选条件。

明细列表（互斥字段，避免多 API 重复展示）：
- country：按国家（ad_unit 为空，有国家代码，含 AA/ZZ）
- ad_unit：按广告单元（无国家代码即 NULL/空串，ad_unit 有值）
- ad_unit_country：按广告单元+国家（有国家代码含 AA/ZZ，ad_unit 有值）

每日汇总使用 build_daily_summary_dimension_filter：
- 同一产品+日期若已有「纯国家」或「纯广告单元」明细，则不再纳入交叉行，避免
  Zhisuo 等 fetch_unit+fetch_country 双 API 与 Addermobi 交叉行叠加重复计数。
"""
from datetime import date
from typing import Any, Optional, Set, Tuple

from sqlalchemy import and_, exists, func, not_, or_, select, tuple_
from sqlalchemy.orm import aliased

CROSS_DIMENSION = "ad_unit_country"
LEGACY_CROSS_DIMENSION = "country_ad_unit"
VALID_DIMENSIONS: Set[str] = frozenset({"country", "ad_unit", CROSS_DIMENSION})
INPUT_DIMENSIONS: Set[str] = VALID_DIMENSIONS | {LEGACY_CROSS_DIMENSION}
DEFAULT_DIMENSION = "country"

# 行级判断用：(product_id, date_iso) 是否存在纯国家 / 纯广告单元明细
ProductDateKey = Tuple[int, str]


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


def row_is_country_only(country_code: Optional[str], ad_unit: Optional[str]) -> bool:
    """纯国家明细（如 Zhisuo 国家报告、无广告单元）。"""
    return row_has_country(country_code) and not (ad_unit or "").strip()


def row_is_ad_unit_only(country_code: Optional[str], ad_unit: Optional[str]) -> bool:
    """纯广告单元明细（如 Zhisuo 广告单元报告、无国家代码）。"""
    return row_has_no_country(country_code) and bool((ad_unit or "").strip())


def row_is_cross_row(country_code: Optional[str], ad_unit: Optional[str]) -> bool:
    """交叉明细（如 Addermobi 单行同时含国家与广告单元）。"""
    return row_has_country(country_code) and bool((ad_unit or "").strip())


def row_is_plain_summary(country_code: Optional[str], ad_unit: Optional[str]) -> bool:
    """Excel 手工导入等：无国家、无广告单元的汇总行。"""
    return row_has_no_country(country_code) and not (ad_unit or "").strip()


def build_dual_api_source_index(rows: list[dict]) -> Tuple[Set[ProductDateKey], Set[ProductDateKey]]:
    """
    从行列表构建「产品+日期」纯国家 / 纯广告单元 索引，供日汇总行级筛选。
    rows 需含 product_id、date（或 date_str）、country_code、ad_unit。
    """
    country_only_keys: Set[ProductDateKey] = set()
    ad_unit_only_keys: Set[ProductDateKey] = set()
    for row in rows:
        pid = row.get("product_id")
        if pid is None:
            continue
        raw_date = row.get("date") or row.get("date_str")
        if raw_date is None:
            continue
        d = raw_date.isoformat() if hasattr(raw_date, "isoformat") else str(raw_date)[:10]
        key = (int(pid), d)
        cc = row.get("country_code")
        au = row.get("ad_unit")
        if row_is_country_only(cc, au):
            country_only_keys.add(key)
        if row_is_ad_unit_only(cc, au):
            ad_unit_only_keys.add(key)
    return country_only_keys, ad_unit_only_keys


def row_matches_daily_summary_dimension_row(
    row: dict,
    dimension: Optional[str],
    *,
    country_only_keys: Optional[Set[ProductDateKey]] = None,
    ad_unit_only_keys: Optional[Set[ProductDateKey]] = None,
) -> bool:
    """
    行级判断：是否纳入每日汇总（镜像 build_daily_summary_dimension_filter 语义）。
    未提供索引时仅按行形态判断（不处理同产品+日期的互斥）。
    """
    dim = normalize_dimension(dimension)
    cc = row.get("country_code")
    au = row.get("ad_unit")
    pid = row.get("product_id")
    raw_date = row.get("date") or row.get("date_str")
    pd_key: Optional[ProductDateKey] = None
    if pid is not None and raw_date is not None:
        d = raw_date.isoformat() if hasattr(raw_date, "isoformat") else str(raw_date)[:10]
        pd_key = (int(pid), d)

    if dim == CROSS_DIMENSION:
        return row_is_cross_row(cc, au)

    if dim == "country":
        if row_is_country_only(cc, au):
            return True
        if row_is_plain_summary(cc, au):
            return True
        if row_is_cross_row(cc, au):
            if country_only_keys is not None and pd_key is not None:
                return pd_key not in country_only_keys
            return True
        return False

    if dim == "ad_unit":
        if row_is_ad_unit_only(cc, au):
            return True
        if row_is_cross_row(cc, au):
            if ad_unit_only_keys is not None and pd_key is not None:
                return pd_key not in ad_unit_only_keys
            return True
        return False

    return False


def build_ad_data_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dimension: Optional[str],
) -> Any:
    """构建明细列表用统计维度筛选（互斥字段，避免多 API 重复计数）。"""
    dim = normalize_dimension(dimension)
    if dim == "country":
        return or_(
            and_(
                _has_country_condition(country_code_column),
                _empty_ad_unit_condition(ad_unit_column),
            ),
            _plain_summary_row_condition(country_code_column, ad_unit_column),
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


def _country_only_row_condition(country_code_column: Any, ad_unit_column: Any) -> Any:
    return and_(
        _has_country_condition(country_code_column),
        _empty_ad_unit_condition(ad_unit_column),
    )


def _ad_unit_only_row_condition(country_code_column: Any, ad_unit_column: Any) -> Any:
    return and_(
        _no_country_condition(country_code_column),
        _non_empty_ad_unit_condition(ad_unit_column),
    )


def _cross_row_condition(country_code_column: Any, ad_unit_column: Any) -> Any:
    return and_(
        _has_country_condition(country_code_column),
        _non_empty_ad_unit_condition(ad_unit_column),
    )


def _plain_summary_row_condition(country_code_column: Any, ad_unit_column: Any) -> Any:
    """无国家且无广告单元（典型 Excel 手工导入行）。"""
    return and_(
        _no_country_condition(country_code_column),
        _empty_ad_unit_condition(ad_unit_column),
    )


def _apply_ad_data_date_bounds(
    query: Any,
    ad_data_model: Any,
    start_date: Optional[date],
    end_date: Optional[date],
) -> Any:
    """限制互斥选源子查询的扫描范围（与外层日期筛选一致）。"""
    if start_date is not None:
        query = query.where(func.date(ad_data_model.date) >= start_date)
    if end_date is not None:
        query = query.where(func.date(ad_data_model.date) <= end_date)
    return query


def _country_only_product_date_pairs_subquery(
    ad_data_model: Any,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """纯国家明细的 (product_id, date) 集合（一次扫描，供 NOT IN 互斥选源）。"""
    query = (
        select(
            ad_data_model.product_id.label("co_product_id"),
            func.date(ad_data_model.date).label("co_date"),
        )
        .where(_country_only_row_condition(ad_data_model.country_code, ad_data_model.ad_unit))
    )
    query = _apply_ad_data_date_bounds(query, ad_data_model, start_date, end_date)
    return query.distinct().subquery("country_only_pd")


def _ad_unit_only_product_date_pairs_subquery(
    ad_data_model: Any,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """纯广告单元明细的 (product_id, date) 集合。"""
    query = (
        select(
            ad_data_model.product_id.label("ao_product_id"),
            func.date(ad_data_model.date).label("ao_date"),
        )
        .where(_ad_unit_only_row_condition(ad_data_model.country_code, ad_data_model.ad_unit))
    )
    query = _apply_ad_data_date_bounds(query, ad_data_model, start_date, end_date)
    return query.distinct().subquery("ad_unit_only_pd")


def _outer_row_not_in_country_only_product_dates(
    ad_data_model: Any,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Any:
    """当前行 product+date 不在纯国家集合中（替代逐行 correlated EXISTS）。"""
    sq = _country_only_product_date_pairs_subquery(ad_data_model, start_date, end_date)
    return tuple_(ad_data_model.product_id, func.date(ad_data_model.date)).notin_(
        select(sq.c.co_product_id, sq.c.co_date)
    )


def _outer_row_not_in_ad_unit_only_product_dates(
    ad_data_model: Any,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Any:
    sq = _ad_unit_only_product_date_pairs_subquery(ad_data_model, start_date, end_date)
    return tuple_(ad_data_model.product_id, func.date(ad_data_model.date)).notin_(
        select(sq.c.ao_product_id, sq.c.ao_date)
    )


def _exists_country_only_same_product_date(ad_data_model: Any) -> Any:
    """同产品+同日是否已有纯国家明细（双 API 国家报告）。"""
    sibling = aliased(ad_data_model)
    return exists(
        select(1).where(
            sibling.product_id == ad_data_model.product_id,
            func.date(sibling.date) == func.date(ad_data_model.date),
            _country_only_row_condition(sibling.country_code, sibling.ad_unit),
        )
    ).correlate(ad_data_model)


def _exists_ad_unit_only_same_product_date(ad_data_model: Any) -> Any:
    """同产品+同日是否已有纯广告单元明细（双 API 单元报告）。"""
    sibling = aliased(ad_data_model)
    return exists(
        select(1).where(
            sibling.product_id == ad_data_model.product_id,
            func.date(sibling.date) == func.date(ad_data_model.date),
            _ad_unit_only_row_condition(sibling.country_code, sibling.ad_unit),
        )
    ).correlate(ad_data_model)


def build_daily_summary_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dimension: Optional[str],
    *,
    ad_data_model: Any = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Any:
    """
    构建每日汇总用统计维度筛选（按产品+日期互斥选源，避免双 API 重复计数）。

    规则（同一 product_id + date）：
    - 按国家：纯国家行；若无纯国家行则使用交叉行（Addermobi 仅交叉数据）
    - 按广告单元：纯广告单元行；若无纯单元行则使用交叉行
    - 按广告单元+国家：仅交叉行

    Zhisuo fetch_unit+fetch_country 同时开启时，同日会有纯国家与纯单元两套数据，
    各自只在对应维度计入，不会与交叉行或另一套 API 加总。
    """
    from app.models.models import AdData

    model = ad_data_model or AdData
    dim = normalize_dimension(dimension)

    if dim == CROSS_DIMENSION:
        return _cross_row_condition(country_code_column, ad_unit_column)

    if dim == "country":
        return or_(
            _country_only_row_condition(country_code_column, ad_unit_column),
            _plain_summary_row_condition(country_code_column, ad_unit_column),
            and_(
                _cross_row_condition(country_code_column, ad_unit_column),
                _outer_row_not_in_country_only_product_dates(model, start_date, end_date),
            ),
        )

    if dim == "ad_unit":
        return or_(
            _ad_unit_only_row_condition(country_code_column, ad_unit_column),
            and_(
                _cross_row_condition(country_code_column, ad_unit_column),
                _outer_row_not_in_ad_unit_only_product_dates(model, start_date, end_date),
            ),
        )

    return _cross_row_condition(country_code_column, ad_unit_column)


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
