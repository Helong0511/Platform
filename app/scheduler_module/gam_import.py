"""
GAM 广告数据专用入库流程。

与通用上游任务不同：
- country 报表 → 交叉行（country_code + ad_unit）
- ad_unit 报表 → 纯广告单元行（country_code 置空）
- site 报表 → 仅校验，不入库（按 ad_unit 汇总后与国家维度交叉校验）
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

GAM_FIELD_MAPPING: dict[str, str] = {
    "date": "date",
    "product_name": "product_name",
    "country_code": "country_code",
    "ad_unit": "ad_unit",
    "request_count": "request_count",
    "match_count": "match_count",
    "display_count": "display_count",
    "click_count": "click_count",
    "revenue_before_deduct": "revenue_before_deduct",
    "viewability_rate": "viewability_rate",
}

GAM_IMPORT_META_FIELDS = frozenset({
    "network_code",
    "report_key",
    "is_leaf_ad_unit",
    "ad_unit_id",
    "site_name",
})

# site 报表中视为「未归因站点」的名称（与 app.scheduler_module.gam_api_fetch 保持一致）
GAM_UNKNOWN_SITE_NAMES = frozenset({"(unknown)", "unknown"})

# 交叉校验对比的数值指标
GAM_VALIDATE_METRICS: tuple[str, ...] = (
    "display_count",
    "click_count",
    "revenue_before_deduct",
    "request_count",
    "match_count",
)

# 通知正文最多展示的明细条数（首条为汇总）
GAM_VALIDATE_NOTIFY_DETAIL_LIMIT = 4


def _importable_row(row: dict[str, Any]) -> dict[str, Any]:
    """去掉 GAM 元数据/auxiliary 字段，保留 process_api_ad_data 所需键。"""
    return {
        key: value
        for key, value in row.items()
        if key not in GAM_IMPORT_META_FIELDS
        and not key.startswith("total_")
        and not key.startswith("ad_exchange_")
        and key not in {
            "coverage_rate",
            "display_rate",
            "click_rate",
            "ecpm_before_deduct",
            "cpc",
        }
    }


def _filter_leaf_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """仅保留可入库的叶子行（校验阶段保留 site_name 等元数据）。"""
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("is_leaf_ad_unit"):
            continue
        if not str(row.get("product_name") or "").strip():
            continue
        filtered.append(row)
    return filtered


def _filter_import_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """仅保留可入库的叶子行。"""
    return [_importable_row(row) for row in _filter_leaf_rows(rows)]


def _reconcile_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    """对账主键：日期 + 产品 + 广告单元。"""
    return (row.get("date"), row.get("product_name"), row.get("ad_unit"))


def _ad_unit_only_key(row: dict[str, Any]) -> tuple[Any, Any]:
    """按广告单元汇总时的对账键（忽略站点维度）。"""
    return (row.get("date"), row.get("ad_unit"))


def _metric_float(row: dict[str, Any], field: str) -> float:
    return float(row.get(field) or 0)


def _metrics_differ(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    tolerance: float,
) -> list[str]:
    """返回差异指标的中文简述列表。"""
    diffs: list[str] = []
    for field in GAM_VALIDATE_METRICS:
        left_val = _metric_float(left, field)
        right_val = _metric_float(right, field)
        if abs(left_val - right_val) > tolerance:
            diffs.append(f"{field} {left_val} vs {right_val}")
    return diffs


def _aggregate_rows_by_key(
    rows: list[dict[str, Any]],
    key_fn,
) -> dict[tuple, dict[str, Any]]:
    """按 key 汇总数值指标，保留首行的 product_name / ad_unit 等维度字段。"""
    buckets: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        key = key_fn(row)
        if key not in buckets:
            buckets[key] = {
                "date": row.get("date"),
                "product_name": row.get("product_name"),
                "ad_unit": row.get("ad_unit"),
                **{field: 0.0 for field in GAM_VALIDATE_METRICS},
            }
        bucket = buckets[key]
        for field in GAM_VALIDATE_METRICS:
            bucket[field] += _metric_float(row, field)
    return buckets


def _format_key_label(key: tuple) -> str:
    if len(key) == 3:
        return f"({key[0]}, {key[1]}, {key[2]!r})"
    if len(key) == 2:
        return f"({key[0]}, {key[1]!r})"
    return repr(key)


def _compare_metric_maps(
    *,
    left_map: dict[tuple, dict[str, Any]],
    right_map: dict[tuple, dict[str, Any]],
    left_label: str,
    right_label: str,
    tolerance: float,
    max_detail: int,
) -> list[str]:
    """对比两份汇总表，返回告警明细（不含汇总行）。"""
    warnings: list[str] = []
    left_keys = set(left_map)
    right_keys = set(right_map)
    only_left = sorted(left_keys - right_keys)
    only_right = sorted(right_keys - left_keys)

    for key in only_left[:max_detail]:
        warnings.append(f"{left_label} 独有键 {_format_key_label(key)}")
    if len(only_left) > max_detail:
        warnings.append(f"{left_label} 独有键另有 {len(only_left) - max_detail} 组未列出")

    for key in only_right[:max_detail]:
        warnings.append(f"{right_label} 独有键 {_format_key_label(key)}")
    if len(only_right) > max_detail:
        warnings.append(f"{right_label} 独有键另有 {len(only_right) - max_detail} 组未列出")

    metric_mismatches = 0
    for key in sorted(left_keys & right_keys):
        diffs = _metrics_differ(
            left_map[key],
            right_map[key],
            tolerance=tolerance,
        )
        if not diffs:
            continue
        metric_mismatches += 1
        if len(warnings) < max_detail:
            warnings.append(
                f"{left_label}/{right_label} 指标不一致 {_format_key_label(key)}: "
                + "; ".join(diffs)
            )
    if metric_mismatches > max_detail:
        warnings.append(
            f"{left_label}/{right_label} 另有 {metric_mismatches - max_detail} 组指标不一致未列出"
        )

    return warnings


def validate_country_vs_ad_unit(
    ad_unit_rows: list[dict[str, Any]],
    country_rows: list[dict[str, Any]],
    *,
    tolerance: float = 0.01,
    max_detail: int = 5,
) -> list[str]:
    """
    country 按 (date, product, ad_unit) 汇总后应与 ad_unit 报表一致。

    country 为 ad_unit 按国家拆分，同一广告单元各国指标之和应等于 ad_unit 行。
    """
    ad_unit_map = {
        _reconcile_key(row): row
        for row in _filter_leaf_rows(ad_unit_rows)
    }
    country_agg = _aggregate_rows_by_key(
        _filter_leaf_rows(country_rows),
        _reconcile_key,
    )
    return _compare_metric_maps(
        left_map=country_agg,
        right_map=ad_unit_map,
        left_label="country合计",
        right_label="ad_unit",
        tolerance=tolerance,
        max_detail=max_detail,
    )


def validate_site_vs_ad_unit(
    ad_unit_rows: list[dict[str, Any]],
    site_rows: list[dict[str, Any]],
    *,
    tolerance: float = 0.01,
    max_detail: int = 5,
) -> list[str]:
    """
    site 按 (date, ad_unit) 跨站点汇总后应与 ad_unit 报表一致。

    site 报表含 SITE_NAME 维度，须先汇总再与 ad_unit 对比，不可按单行 site_name 对账。
    """
    ad_unit_filtered = _filter_leaf_rows(ad_unit_rows)
    site_filtered = _filter_leaf_rows(site_rows)

    ad_unit_by_unit = {
        _ad_unit_only_key(row): row
        for row in ad_unit_filtered
    }
    site_agg = _aggregate_rows_by_key(site_filtered, _ad_unit_only_key)

    warnings = _compare_metric_maps(
        left_map=site_agg,
        right_map=ad_unit_by_unit,
        left_label="site合计",
        right_label="ad_unit",
        tolerance=tolerance,
        max_detail=max_detail,
    )

    # 站点归因诊断：汇总仍不足时，统计 unknown 站点占比
    unknown_display: dict[tuple, float] = defaultdict(float)
    for row in site_filtered:
        site_name = str(row.get("site_name") or "").strip().lower()
        if site_name not in GAM_UNKNOWN_SITE_NAMES:
            continue
        unknown_display[_ad_unit_only_key(row)] += _metric_float(row, "display_count")

    attribution_notes = 0
    for key, ad_row in ad_unit_by_unit.items():
        ad_display = _metric_float(ad_row, "display_count")
        site_display = _metric_float(site_agg.get(key, {}), "display_count")
        gap = ad_display - site_display
        if gap <= tolerance:
            continue
        unknown = unknown_display.get(key, 0.0)
        if unknown <= tolerance:
            continue
        attribution_notes += 1
        if len(warnings) >= max_detail:
            continue
        warnings.append(
            f"站点归因: {_format_key_label(key)} ad_unit展示 {ad_display}，"
            f"site合计 {site_display}，unknown站点 {unknown}"
        )
    if attribution_notes > max(0, max_detail - len(warnings)):
        extra = attribution_notes - max(0, max_detail - len(warnings))
        if extra > 0:
            warnings.append(f"站点归因说明另有 {extra} 组未列出")

    return warnings


def validate_gam_reports(
    ad_unit_rows: list[dict[str, Any]],
    site_rows: list[dict[str, Any]],
    country_rows: list[dict[str, Any]] | None = None,
    *,
    tolerance: float = 0.01,
    max_detail: int = 5,
) -> list[str]:
    """
    GAM 三报表全面交叉校验。

    未拉取 ad_unit 时跳过 country/site 对账（避免「仅 country」配置产生误报）。
    返回告警列表；首条为汇总，其后为明细。全部通过时返回空列表。
    """
    country_warnings: list[str] = []
    if ad_unit_rows and country_rows:
        country_warnings = validate_country_vs_ad_unit(
            ad_unit_rows,
            country_rows,
            tolerance=tolerance,
            max_detail=max_detail,
        )

    site_warnings: list[str] = []
    if ad_unit_rows and site_rows:
        site_warnings = validate_site_vs_ad_unit(
            ad_unit_rows,
            site_rows,
            tolerance=tolerance,
            max_detail=max_detail,
        )

    if not country_warnings and not site_warnings:
        return []

    ad_unit_count = len(_filter_leaf_rows(ad_unit_rows))
    country_count = len(_filter_leaf_rows(country_rows or []))
    site_count = len(_filter_leaf_rows(site_rows))

    summary = (
        f"校验摘要: ad_unit {ad_unit_count} 行, country {country_count} 行, site {site_count} 行; "
        f"country差异 {len(country_warnings)} 项, site差异 {len(site_warnings)} 项"
    )

    details: list[str] = []
    details.extend(country_warnings)
    details.extend(site_warnings)
    return [summary, *details]


def prepare_country_import_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """country 报表：保留国家+广告单元交叉行。"""
    prepared: list[dict[str, Any]] = []
    for row in _filter_import_rows(rows):
        if not str(row.get("country_code") or "").strip():
            continue
        prepared.append(dict(row))
    return prepared


def prepare_ad_unit_import_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ad_unit 报表：强制纯广告单元形态（无国家代码）。"""
    prepared: list[dict[str, Any]] = []
    for row in _filter_import_rows(rows):
        item = dict(row)
        item["country_code"] = ""
        prepared.append(item)
    return prepared


async def import_gam_account_bundle(
    bundle: dict[str, Any],
    *,
    task_name: str,
    current_time_str: str,
) -> str:
    """
    单账号 GAM bundle 入库：country 交叉行；ad_unit 仅在校验且无 country 数据时入库；site 仅校验。
    """
    network_code = str(bundle.get("network_code") or "")
    account_key = str(bundle.get("account_key") or "")
    reports: dict[str, list[dict[str, Any]]] = bundle.get("reports") or {}

    ad_unit_rows = list(reports.get("ad_unit") or [])
    country_rows = list(reports.get("country") or [])
    site_rows = list(reports.get("site") or [])

    validation_warnings = validate_gam_reports(
        ad_unit_rows,
        site_rows,
        country_rows,
    )
    if validation_warnings:
        for warning in validation_warnings:
            logger.warning("GAM 校验 [%s]: %s", account_key, warning)
    else:
        logger.info(
            "GAM 校验 [%s]: country/site 与 ad_unit 全部对齐",
            account_key,
        )

    notify_params = {
        "账号": account_key,
        "网络": network_code,
        "起始日期": bundle.get("start_date"),
        "终止日期": bundle.get("end_date"),
    }
    if validation_warnings:
        notify_params["校验告警"] = "; ".join(
            validation_warnings[: GAM_VALIDATE_NOTIFY_DETAIL_LIMIT + 1]
        )

    phase_summaries: list[str] = []

    country_import_rows = prepare_country_import_rows(country_rows)
    if country_import_rows:
        country_summary = await import_upstream_ad_data(
            task_name=task_name,
            data=country_import_rows,
            field_mapping=GAM_FIELD_MAPPING,
            source=f"GAM-{network_code}-country",
            current_time_str=current_time_str,
            notify_title=f"GAM-{account_key}-country",
            update_task_result=False,
            notify_params=notify_params,
        )
        phase_summaries.append(f"country({len(country_import_rows)}行): {country_summary}")
    else:
        phase_summaries.append("country: 无数据")

    ad_unit_import_rows = prepare_ad_unit_import_rows(ad_unit_rows)
    if country_import_rows:
        # country 已是「日期+产品+广告单元+国家」交叉明细；再入库 ad_unit 纯单元行会导致
        # 广告单元日汇总互斥选源只计纯单元（常少于交叉合计），与每日统计/国家数据不一致。
        ad_unit_count = len(ad_unit_import_rows)
        phase_summaries.append(
            f"ad_unit({ad_unit_count}行): 仅校验不入库（已有 country 交叉数据）"
        )
    elif ad_unit_import_rows:
        ad_unit_summary = await import_upstream_ad_data(
            task_name=task_name,
            data=ad_unit_import_rows,
            field_mapping=GAM_FIELD_MAPPING,
            source=f"GAM-{network_code}-ad_unit",
            current_time_str=current_time_str,
            notify_title=f"GAM-{account_key}-ad_unit",
            update_task_result=True,
            notify_params=notify_params,
        )
        phase_summaries.append(f"ad_unit({len(ad_unit_import_rows)}行): {ad_unit_summary}")
    else:
        phase_summaries.append("ad_unit: 无数据")

    site_count = len(_filter_leaf_rows(site_rows))
    phase_summaries.append(f"site({site_count}行): 仅校验不入库")

    bundle_warnings = list(bundle.get("warnings") or [])
    if bundle_warnings:
        phase_summaries.append("拉数告警: " + "; ".join(bundle_warnings))

    return "; ".join(phase_summaries)
