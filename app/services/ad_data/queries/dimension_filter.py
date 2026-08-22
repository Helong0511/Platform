"""
广告数据统计维度筛选条件。

明细列表（data_type=all / 明细维护）：
- country：有具体国家且 ad_unit 为空（含 AA；不含 ZZ）
- ad_unit：ad_unit 有值且无具体国家（NULL/空串/ZZ）
- ad_unit_country：与日汇总交叉选源对齐——report_type=cross，
  或 legacy 行且具体国家与 ad_unit 均有值（避免 day 能拉到、all 拉不到）

ZZ（全部区域）规则：
- ZZ + 广告单元非空 → 广告单元维度
- ZZ + 广告单元为空 → 日报维度（日汇总 country 选源时作为 daily 纳入）

每日汇总使用 build_daily_summary_dimension_filter：
- 优先按 report_type 选源（country > cross > unit > daily）
- 同日 API 国家 + API 日报：只留国家；Excel 日报与 API 国家仍相加
- legacy 行仍按行形态互斥选源，与迁移前行为兼容
"""
from datetime import date
from typing import Any, Optional, Set, Tuple

from sqlalchemy import and_, exists, func, or_, select, tuple_
from sqlalchemy.orm import aliased

from app.core.ad_data_metadata import (
    DATA_SOURCE_EXCEL,
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_CROSS,
    REPORT_TYPE_DAILY,
    REPORT_TYPE_LEGACY,
    REPORT_TYPE_UNIT,
    get_standard_report_type,
)
from app.core.country_code import (
    ALL_REGIONS_COUNTRY_CODE,
    has_concrete_country_code,
)

CROSS_DIMENSION = "ad_unit_country"
LEGACY_CROSS_DIMENSION = "country_ad_unit"
DETAIL_ALL_DIMENSION = "all"
VALID_DIMENSIONS: Set[str] = frozenset({"country", "ad_unit", CROSS_DIMENSION})
LIST_DIMENSIONS: Set[str] = VALID_DIMENSIONS | {DETAIL_ALL_DIMENSION, LEGACY_CROSS_DIMENSION}
INPUT_DIMENSIONS: Set[str] = VALID_DIMENSIONS | {LEGACY_CROSS_DIMENSION, DETAIL_ALL_DIMENSION}
DEFAULT_DIMENSION = "country"

# 行级判断用：(product_id, date_iso) 是否存在纯国家 / 纯广告单元明细
ProductDateKey = Tuple[int, str]


def normalize_list_dimension(dimension: Optional[str]) -> str:
    """明细列表/导出用维度解析（含全部明细）。"""
    if not dimension:
        return DEFAULT_DIMENSION
    stripped = str(dimension).strip()
    if stripped == DETAIL_ALL_DIMENSION:
        return DETAIL_ALL_DIMENSION
    return normalize_dimension(stripped)


def is_all_list_dimension(dimension: Optional[str]) -> bool:
    return str(dimension or "").strip() == DETAIL_ALL_DIMENSION


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
    if stripped == DETAIL_ALL_DIMENSION:
        return DETAIL_ALL_DIMENSION
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
            f"ad_unit_country（按广告单元+国家）、all（原始全量明细）；country_ad_unit 为兼容别名"
        )
    if stripped == DETAIL_ALL_DIMENSION:
        return DETAIL_ALL_DIMENSION
    return normalize_dimension(stripped)


def maybe_build_ad_data_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dimension: Optional[str],
    *,
    report_type_column: Any = None,
) -> Any | None:
    """未传 dimension 时返回 None；传入合法 dimension 时返回筛选条件。"""
    dim = parse_optional_dimension(dimension)
    if dim is None:
        return None
    return build_ad_data_dimension_filter(
        country_code_column,
        ad_unit_column,
        dim,
        report_type_column=report_type_column,
    )


def _empty_ad_unit_condition(ad_unit_column: Any) -> Any:
    normalized = func.trim(ad_unit_column)
    return or_(ad_unit_column.is_(None), normalized == "")


def _non_empty_ad_unit_condition(ad_unit_column: Any) -> Any:
    normalized = func.trim(ad_unit_column)
    return and_(ad_unit_column.isnot(None), normalized != "")


def _no_country_condition(country_code_column: Any) -> Any:
    """无具体国家：NULL、空串或 ZZ（全部区域）。"""
    normalized = func.trim(country_code_column)
    return or_(
        country_code_column.is_(None),
        normalized == "",
        normalized == ALL_REGIONS_COUNTRY_CODE,
    )


def _has_country_condition(country_code_column: Any) -> Any:
    """有具体国家：非空且非 ZZ（含 AA 等特殊代码）。"""
    normalized = func.trim(country_code_column)
    return and_(
        country_code_column.isnot(None),
        normalized != "",
        normalized != ALL_REGIONS_COUNTRY_CODE,
    )


def row_has_country(country_code: Optional[str]) -> bool:
    """行级判断：是否有具体国家代码（含 AA；不含 ZZ）。"""
    return has_concrete_country_code(country_code)


def row_has_no_country(country_code: Optional[str]) -> bool:
    """行级判断：是否无具体国家代码（NULL/空串/ZZ）。"""
    return not row_has_country(country_code)


def row_is_country_only(country_code: Optional[str], ad_unit: Optional[str]) -> bool:
    """纯国家明细（如 Zhisuo 国家报告、无广告单元；不含 ZZ）。"""
    return row_has_country(country_code) and not (ad_unit or "").strip()


def row_is_ad_unit_only(country_code: Optional[str], ad_unit: Optional[str]) -> bool:
    """纯广告单元明细（无具体国家；含 ZZ + 有广告单元）。"""
    return row_has_no_country(country_code) and bool((ad_unit or "").strip())


def row_is_cross_row(country_code: Optional[str], ad_unit: Optional[str]) -> bool:
    """交叉明细（具体国家 + 广告单元；不含 ZZ）。"""
    return row_has_country(country_code) and bool((ad_unit or "").strip())


def row_is_plain_summary(country_code: Optional[str], ad_unit: Optional[str]) -> bool:
    """日报/手工汇总行：无具体国家、无广告单元（含 ZZ）。"""
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


def row_is_excel_data_source(data_source: Optional[str]) -> bool:
    """是否为 Excel 导入来源（与 API 日报区分：Excel 可与 API 国家同日相加）。"""
    return str(data_source or "").strip().lower() == DATA_SOURCE_EXCEL


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
            # Excel 日报始终可与 API 国家相加；API 日报仅在无国家行时兜底
            if row_is_excel_data_source(row.get("data_source")):
                return True
            if country_only_keys is not None and pd_key is not None:
                return pd_key not in country_only_keys
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


def _legacy_row_condition(report_type_column: Any) -> Any:
    """历史行：report_type 为 legacy 或未标注。"""
    if report_type_column is None:
        return None
    return or_(
        report_type_column == REPORT_TYPE_LEGACY,
        report_type_column.is_(None),
    )


def _explicit_report_type_in(report_type_column: Any, *types: str) -> Any:
    return report_type_column.in_(types)


def build_ad_data_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dimension: Optional[str],
    *,
    report_type_column: Any = None,
) -> Any:
    """构建明细列表用统计维度筛选。

    - country / ad_unit：按字段有无互斥筛选
    - ad_unit_country：与日汇总交叉选源对齐（report_type=cross 或 legacy 交叉形态），
      避免出现 day 能汇总、all 明细却为空的情况
    """
    if is_all_list_dimension(dimension):
        from sqlalchemy import true

        return true()

    dim = normalize_dimension(dimension)
    if dim == CROSS_DIMENSION and report_type_column is not None:
        # 必须同时满足交叉行形态，避免历史误标 report_type=cross 的 ZZ 行混入
        return or_(
            and_(
                report_type_column == REPORT_TYPE_CROSS,
                _cross_row_condition(country_code_column, ad_unit_column),
            ),
            and_(
                _legacy_row_condition(report_type_column),
                _cross_row_condition(country_code_column, ad_unit_column),
            ),
        )
    return _shape_dimension_filter(country_code_column, ad_unit_column, dim)


def _shape_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dim: str,
) -> Any:
    """明细列表：按 country_code / ad_unit 字段有无互斥筛选。"""
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
    """无国家且无广告单元（典型 Excel 手工导入行 / API 日报）。"""
    return and_(
        _no_country_condition(country_code_column),
        _empty_ad_unit_condition(ad_unit_column),
    )


def _excel_data_source_condition(data_source_column: Any) -> Any:
    return data_source_column == DATA_SOURCE_EXCEL


def _plain_summary_for_country_dimension(
    country_code_column: Any,
    ad_unit_column: Any,
    model: Any,
    start_date: Optional[date],
    end_date: Optional[date],
) -> Any:
    """
    country 日汇总中的日报/plain 行：

    - Excel：始终纳入（可与 API 国家同日相加）
    - 非 Excel（API 日报等）：仅当同产品同日无国家行时兜底
    """
    plain = _plain_summary_row_condition(country_code_column, ad_unit_column)
    data_source_col = getattr(model, "data_source", None)
    no_country_same_day = _outer_row_not_in_country_only_product_dates(
        model, start_date, end_date
    )
    if data_source_col is None:
        return and_(plain, no_country_same_day)
    return and_(
        plain,
        or_(
            _excel_data_source_condition(data_source_col),
            no_country_same_day,
        ),
    )


def _apply_ad_data_date_bounds(
    query: Any,
    ad_data_model: Any,
    start_date: Optional[date],
    end_date: Optional[date],
) -> Any:
    """限制互斥选源子查询的扫描范围（与外层日期筛选一致）。"""
    if start_date is not None:
        query = query.where(ad_data_model.date >= start_date)
    if end_date is not None:
        query = query.where(ad_data_model.date <= end_date)
    return query


def _report_type_product_date_pairs_subquery(
    ad_data_model: Any,
    report_type: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """指定 report_type 的 (product_id, date) 集合。"""
    col_prefix = report_type.replace("-", "_")[:8]
    query = (
        select(
            ad_data_model.product_id.label(f"{col_prefix}_product_id"),
            ad_data_model.date.label(f"{col_prefix}_date"),
        )
        .where(ad_data_model.report_type == report_type)
    )
    query = _apply_ad_data_date_bounds(query, ad_data_model, start_date, end_date)
    return query.distinct().subquery(f"rt_{col_prefix}_pd")


def _report_type_product_date_pairs_by_source_subquery(
    ad_data_model: Any,
    report_type: str,
    data_source: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """指定 report_type + data_source 的 (product_id, date) 集合。"""
    col_prefix = f"{report_type}_{data_source}"[:16]
    query = (
        select(
            ad_data_model.product_id.label(f"{col_prefix}_product_id"),
            ad_data_model.date.label(f"{col_prefix}_date"),
        )
        .where(
            ad_data_model.report_type == report_type,
            ad_data_model.data_source == data_source,
        )
    )
    query = _apply_ad_data_date_bounds(query, ad_data_model, start_date, end_date)
    return query.distinct().subquery(f"rt_{col_prefix}_pd")


def _outer_row_not_in_report_type_product_dates(
    ad_data_model: Any,
    report_type: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Any:
    sq = _report_type_product_date_pairs_subquery(
        ad_data_model, report_type, start_date, end_date
    )
    pid_col = list(sq.c)[0]
    date_col = list(sq.c)[1]
    return tuple_(ad_data_model.product_id, ad_data_model.date).notin_(
        select(pid_col, date_col)
    )


def _outer_row_not_in_report_type_for_source(
    ad_data_model: Any,
    report_type: str,
    data_source: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Any:
    """排除指定数据源+report_type 存在的 (product_id, date) 组合。"""
    sq = _report_type_product_date_pairs_by_source_subquery(
        ad_data_model, report_type, data_source, start_date, end_date
    )
    pid_col = list(sq.c)[0]
    date_col = list(sq.c)[1]
    return tuple_(ad_data_model.product_id, ad_data_model.date).notin_(
        select(pid_col, date_col)
    )


def _country_only_product_date_pairs_subquery(
    ad_data_model: Any,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """纯国家明细的 (product_id, date) 集合（report_type + legacy 行形态）。"""
    query = (
        select(
            ad_data_model.product_id.label("co_product_id"),
            ad_data_model.date.label("co_date"),
        )
        .where(
            or_(
                ad_data_model.report_type == REPORT_TYPE_COUNTRY,
                and_(
                    _legacy_row_condition(ad_data_model.report_type),
                    _country_only_row_condition(
                        ad_data_model.country_code, ad_data_model.ad_unit
                    ),
                ),
            )
        )
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
            ad_data_model.date.label("ao_date"),
        )
        .where(
            or_(
                ad_data_model.report_type == REPORT_TYPE_UNIT,
                and_(
                    _legacy_row_condition(ad_data_model.report_type),
                    _ad_unit_only_row_condition(
                        ad_data_model.country_code, ad_data_model.ad_unit
                    ),
                ),
            )
        )
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
    return tuple_(ad_data_model.product_id, ad_data_model.date).notin_(
        select(sq.c.co_product_id, sq.c.co_date)
    )


def _outer_row_not_in_ad_unit_only_product_dates(
    ad_data_model: Any,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Any:
    sq = _ad_unit_only_product_date_pairs_subquery(ad_data_model, start_date, end_date)
    return tuple_(ad_data_model.product_id, ad_data_model.date).notin_(
        select(sq.c.ao_product_id, sq.c.ao_date)
    )


def _unit_fallback_for_country_dimension(
    country_code_column: Any,
    ad_unit_column: Any,
    model: Any,
    start_date: Optional[date],
    end_date: Optional[date],
    *,
    rt_col: Any = None,
    legacy_shape: Any = None,
) -> Any:
    """
    country 日汇总兜底：同产品同日无国家/交叉数据时纳入纯单元行。

    适用仅 unit 维度的上游（如 SweetStaste、PlayHorizonx）；互斥优先级 country > cross > unit。
    """
    unit_row = _ad_unit_only_row_condition(country_code_column, ad_unit_column)
    no_country = _outer_row_not_in_country_only_product_dates(
        model, start_date, end_date
    )
    no_cross = _outer_row_not_in_report_type_product_dates(
        model, REPORT_TYPE_CROSS, start_date, end_date
    )
    if rt_col is not None and legacy_shape is not None:
        typed = or_(
            and_(rt_col == REPORT_TYPE_UNIT, unit_row),
            and_(legacy_shape, unit_row),
        )
        return and_(typed, no_country, no_cross)
    return and_(unit_row, no_country, no_cross)


def _exists_country_only_same_product_date(ad_data_model: Any) -> Any:
    """同产品+同日是否已有纯国家明细（双 API 国家报告）。"""
    sibling = aliased(ad_data_model)
    return exists(
        select(1).where(
            sibling.product_id == ad_data_model.product_id,
            sibling.date == ad_data_model.date,
            _country_only_row_condition(sibling.country_code, sibling.ad_unit),
        )
    ).correlate(ad_data_model)


def _exists_ad_unit_only_same_product_date(ad_data_model: Any) -> Any:
    """同产品+同日是否已有纯广告单元明细（双 API 单元报告）。"""
    sibling = aliased(ad_data_model)
    return exists(
        select(1).where(
            sibling.product_id == ad_data_model.product_id,
            sibling.date == ad_data_model.date,
            _ad_unit_only_row_condition(sibling.country_code, sibling.ad_unit),
        )
    ).correlate(ad_data_model)


def kpi_mutual_source_filter(
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    dimension: Optional[str] = None,
    ad_data_model: Any = None,
    data_source: Optional[str] = None,
) -> Any:
    """
    KPI / 仪表盘 / Telegram 汇总用互斥选源。

    默认与日汇总不传 dimension 一致（country），避免同日多报表来源 SUM 重复。
    支持按 data_source 指定标准维度（如 Aya 的标准维度为 daily）。
    """
    from app.models.models import AdData

    model = ad_data_model or AdData
    return build_daily_summary_dimension_filter(
        model.country_code,
        model.ad_unit,
        normalize_dimension(dimension),
        ad_data_model=model,
        start_date=start_date,
        end_date=end_date,
        data_source=data_source,
    )


def build_daily_summary_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dimension: Optional[str],
    *,
    ad_data_model: Any = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    data_source: Optional[str] = None,
) -> Any:
    """
    构建每日汇总用统计维度筛选（按产品+日期互斥选源，避免双 API 重复计数）。

    有 report_type 时按类型选源；legacy 行仍按行形态互斥。
    支持按 data_source 指定标准维度（如 Aya 的标准维度为 daily）。
    """
    from app.models.models import AdData

    model = ad_data_model or AdData
    dim = normalize_dimension(dimension)
    rt_col = getattr(model, "report_type", None)
    ds_col = getattr(model, "data_source", None)

    if rt_col is None:
        return _legacy_daily_summary_dimension_filter(
            country_code_column, ad_unit_column, dim, model, start_date, end_date
        )

    standard_rt = get_standard_report_type(data_source) if data_source else None
    has_source_standard = bool(standard_rt and ds_col is not None)

    legacy_shape = _legacy_row_condition(rt_col)

    if dim == CROSS_DIMENSION:
        return or_(
            and_(
                rt_col == REPORT_TYPE_CROSS,
                _cross_row_condition(country_code_column, ad_unit_column),
            ),
            and_(legacy_shape, _cross_row_condition(country_code_column, ad_unit_column)),
        )

    if dim == "country":
        plain_for_country = _plain_summary_for_country_dimension(
            country_code_column,
            ad_unit_column,
            model,
            start_date,
            end_date,
        )

        # 如果数据源有标准维度（如 Aya 标准= daily），则：
        # 1. 标准维度的数据直接保留
        # 2. 非标准维度的数据仅在标准维度不存在时保留
        if has_source_standard:
            source_standard = and_(
                ds_col == data_source,
                rt_col == standard_rt,
                _plain_summary_row_condition(country_code_column, ad_unit_column),
            )
            source_fallback = and_(
                ds_col == data_source,
                rt_col != standard_rt,
                _outer_row_not_in_report_type_for_source(
                    model, standard_rt, data_source, start_date, end_date
                ),
            )
            other_sources = and_(
                ds_col != data_source,
                or_(
                    and_(
                        rt_col == REPORT_TYPE_COUNTRY,
                        _country_only_row_condition(country_code_column, ad_unit_column),
                    ),
                    plain_for_country,
                    and_(
                        rt_col == REPORT_TYPE_CROSS,
                        _cross_row_condition(country_code_column, ad_unit_column),
                        _outer_row_not_in_report_type_product_dates(
                            model, REPORT_TYPE_COUNTRY, start_date, end_date
                        ),
                    ),
                    and_(
                        legacy_shape,
                        or_(
                            _country_only_row_condition(country_code_column, ad_unit_column),
                            and_(
                                _cross_row_condition(country_code_column, ad_unit_column),
                                _outer_row_not_in_country_only_product_dates(
                                    model, start_date, end_date
                                ),
                            ),
                        ),
                    ),
                ),
            )
            return or_(source_standard, source_fallback, other_sources)

        return or_(
            and_(
                rt_col == REPORT_TYPE_COUNTRY,
                _country_only_row_condition(country_code_column, ad_unit_column),
            ),
            plain_for_country,
            and_(
                rt_col == REPORT_TYPE_CROSS,
                _cross_row_condition(country_code_column, ad_unit_column),
                _outer_row_not_in_report_type_product_dates(
                    model, REPORT_TYPE_COUNTRY, start_date, end_date
                ),
            ),
            _unit_fallback_for_country_dimension(
                country_code_column,
                ad_unit_column,
                model,
                start_date,
                end_date,
                rt_col=rt_col,
                legacy_shape=legacy_shape,
            ),
            and_(
                legacy_shape,
                or_(
                    _country_only_row_condition(country_code_column, ad_unit_column),
                    and_(
                        _cross_row_condition(country_code_column, ad_unit_column),
                        _outer_row_not_in_country_only_product_dates(
                            model, start_date, end_date
                        ),
                    ),
                ),
            ),
        )

    if dim == "ad_unit":
        # 如果数据源有标准维度（如 Aya 标准= daily），则：
        # 1. 标准维度的数据直接保留
        # 2. 非标准维度的数据仅在标准维度不存在时保留
        if has_source_standard:
            source_standard = and_(
                ds_col == data_source,
                rt_col == standard_rt,
                _plain_summary_row_condition(country_code_column, ad_unit_column),
            )
            source_fallback = and_(
                ds_col == data_source,
                rt_col != standard_rt,
                _outer_row_not_in_report_type_for_source(
                    model, standard_rt, data_source, start_date, end_date
                ),
            )
            other_sources = and_(
                ds_col != data_source,
                or_(
                    and_(
                        rt_col == REPORT_TYPE_UNIT,
                        _ad_unit_only_row_condition(country_code_column, ad_unit_column),
                    ),
                    _ad_unit_only_row_condition(country_code_column, ad_unit_column),
                    and_(
                        rt_col == REPORT_TYPE_CROSS,
                        _cross_row_condition(country_code_column, ad_unit_column),
                        _outer_row_not_in_report_type_product_dates(
                            model, REPORT_TYPE_UNIT, start_date, end_date
                        ),
                    ),
                    and_(
                        legacy_shape,
                        and_(
                            _cross_row_condition(country_code_column, ad_unit_column),
                            _outer_row_not_in_ad_unit_only_product_dates(
                                model, start_date, end_date
                            ),
                        ),
                    ),
                ),
            )
            return or_(source_standard, source_fallback, other_sources)

        return or_(
            and_(
                rt_col == REPORT_TYPE_UNIT,
                _ad_unit_only_row_condition(country_code_column, ad_unit_column),
            ),
            _ad_unit_only_row_condition(country_code_column, ad_unit_column),
            and_(
                rt_col == REPORT_TYPE_CROSS,
                _cross_row_condition(country_code_column, ad_unit_column),
                _outer_row_not_in_report_type_product_dates(
                    model, REPORT_TYPE_UNIT, start_date, end_date
                ),
            ),
            and_(
                legacy_shape,
                and_(
                    _cross_row_condition(country_code_column, ad_unit_column),
                    _outer_row_not_in_ad_unit_only_product_dates(
                        model, start_date, end_date
                    ),
                ),
            ),
        )

    return _cross_row_condition(country_code_column, ad_unit_column)


def _legacy_daily_summary_dimension_filter(
    country_code_column: Any,
    ad_unit_column: Any,
    dim: str,
    model: Any,
    start_date: Optional[date],
    end_date: Optional[date],
) -> Any:
    """无 report_type 列时的行形态互斥选源（与迁移前一致）。"""
    if dim == CROSS_DIMENSION:
        return _cross_row_condition(country_code_column, ad_unit_column)

    if dim == "country":
        return or_(
            _country_only_row_condition(country_code_column, ad_unit_column),
            _plain_summary_for_country_dimension(
                country_code_column,
                ad_unit_column,
                model,
                start_date,
                end_date,
            ),
            and_(
                _cross_row_condition(country_code_column, ad_unit_column),
                _outer_row_not_in_country_only_product_dates(model, start_date, end_date),
            ),
            _unit_fallback_for_country_dimension(
                country_code_column,
                ad_unit_column,
                model,
                start_date,
                end_date,
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
    if is_all_list_dimension(dimension):
        return True
    return normalize_dimension(dimension) != "ad_unit"


def ad_unit_exact_filter_applies(dimension: Optional[str]) -> bool:
    """按国家维度时无广告单元数据，广告单元精确筛选不适用。"""
    if is_all_list_dimension(dimension):
        return True
    return normalize_dimension(dimension) != "country"
