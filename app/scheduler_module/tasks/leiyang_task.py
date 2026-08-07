"""
LeiYang 上游广告数据拉取定时任务。

功能说明：
- 从 DataManager（datamanager.leiyanggame.com）拉取外部报表
- 默认拉取国家维度（/reports/country），可通过环境变量开启广告位 / 聚合维度
- 经字段映射与去重写入 ad_data 表

鉴权方式：X-API-Key
接口文档：tests/LeiYang API/对接API文档.pdf
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.ad_data_metadata import (
    DATA_SOURCE_LEIYANG,
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_DAILY,
    REPORT_TYPE_UNIT,
)
from app.core.config import settings
from app.scheduler_module.task_names import LEIYANG_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import log_scheduled_task_skip, resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import (
    LEIYANG_PATH_COUNTRY,
    LEIYANG_PATH_DAILY,
    LEIYANG_PATH_UNIT,
    fetch_leiyang_rows,
)
from app.scheduler_module.upstream_http import UpstreamTransientError
from app.scheduler_module.upstream_task_runner import (
    UpstreamTaskOutcome,
    run_upstream_import_task,
)

logger = logging.getLogger(__name__)

# 公共指标映射（真实响应为 PascalCase；文档 camelCase 作兼容回退，在 preprocess 里归一）
LEIYANG_COMMON_FIELD_MAPPING: dict[str, str] = {
    "date": "date_resolved",
    "product_name": "product_name_resolved",
    "request_count": "requests_resolved",
    "match_count": "match_requests_resolved",
    "display_count": "impressions_resolved",
    "click_count": "clicks_resolved",
    "coverage_rate": "coverage_rate_resolved",
    "click_rate": "click_rate_resolved",
    "revenue_before_deduct": "revenue_resolved",
    "ecpm_before_deduct": "ecpm_resolved",
}

LEIYANG_COUNTRY_FIELD_MAPPING: dict[str, str] = {
    **LEIYANG_COMMON_FIELD_MAPPING,
    "country_code": "country_resolved",
}

# ad-unit 接口含 Country + AdUnit*；Country=ALL 时按无具体国家处理
LEIYANG_UNIT_FIELD_MAPPING: dict[str, str] = {
    **LEIYANG_COMMON_FIELD_MAPPING,
    "country_code": "country_resolved",
    "ad_unit": "ad_unit_resolved",
}

LEIYANG_DAILY_FIELD_MAPPING: dict[str, str] = dict(LEIYANG_COMMON_FIELD_MAPPING)

_LEIYANG_REPORTS: list[dict[str, Any]] = [
    {
        "env_flag": "LEIYANG_API_FETCH_COUNTRY",
        "path": LEIYANG_PATH_COUNTRY,
        "label": "LeiYang country",
        "mapping": LEIYANG_COUNTRY_FIELD_MAPPING,
        "dimension": REPORT_TYPE_COUNTRY,
        "report_type": REPORT_TYPE_COUNTRY,
    },
    {
        "env_flag": "LEIYANG_API_FETCH_UNIT",
        "path": LEIYANG_PATH_UNIT,
        "label": "LeiYang ad-unit",
        "mapping": LEIYANG_UNIT_FIELD_MAPPING,
        "dimension": REPORT_TYPE_UNIT,
        "report_type": REPORT_TYPE_UNIT,
    },
    {
        "env_flag": "LEIYANG_API_FETCH_DAILY",
        "path": LEIYANG_PATH_DAILY,
        "label": "LeiYang all",
        "mapping": LEIYANG_DAILY_FIELD_MAPPING,
        "dimension": REPORT_TYPE_DAILY,
        "report_type": REPORT_TYPE_DAILY,
    },
]


def _is_report_enabled(flag: str) -> bool:
    return bool(getattr(settings, flag, False))


def _pick_first(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item.get(key) is not None and str(item.get(key)).strip() != "":
            return item.get(key)
    return None


def _to_percent(value: Any) -> float:
    """将上游 0-1 比率转为平台常用百分比；已是百分比则原样保留。"""
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return 0.0
    if rate < 0:
        return 0.0
    if rate <= 1.0:
        return rate * 100.0
    return rate


def _resolve_date(value: Any) -> str:
    """兼容 YYYY-MM-DD 与 ISO 日期时间（如 2026-02-06T00:00:00+08:00）。"""
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def _resolve_country(value: Any) -> str:
    """ALL/-1/未知 视为无具体国家；其余转大写。"""
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in {
        "ALL",
        "ALL REGIONS",
        "WORLD",
        "ZZ",
        "全球",
        "全部",
        "全部区域",
        "-1",
        "-2",
        "-4",
        "NONE",
        "NULL",
        "N/A",
        "NA",
        "UNKNOWN",
        "--",
    }:
        return ""
    return upper


def preprocess_leiyang_rows(ad_data: list[Any]) -> list[Any]:
    """归一 PascalCase/camelCase 字段，并转换日期、国家、比率。"""
    for item in ad_data:
        package = str(_pick_first(item, "PackageName", "packageName") or "").strip()
        app_id = str(_pick_first(item, "AppID", "appId", "AppId") or "").strip()
        # 包名更适合产品匹配；AppID 多为内部哈希
        item["product_name_resolved"] = package or app_id

        unit_name = str(_pick_first(item, "AdUnitName", "adUnitName") or "").strip()
        unit_id = str(_pick_first(item, "AdUnitID", "AdUnitId", "adUnitId") or "").strip()
        item["ad_unit_resolved"] = unit_name or unit_id

        item["date_resolved"] = _resolve_date(_pick_first(item, "Date", "date"))
        item["country_resolved"] = _resolve_country(_pick_first(item, "Country", "country"))
        item["requests_resolved"] = _pick_first(item, "Requests", "requests") or 0
        item["match_requests_resolved"] = _pick_first(item, "MatchRequests", "matchRequests") or 0
        item["impressions_resolved"] = _pick_first(item, "Impressions", "impressions") or 0
        item["clicks_resolved"] = _pick_first(item, "Clicks", "clicks") or 0
        item["revenue_resolved"] = _pick_first(item, "Revenue", "revenue") or 0
        item["ecpm_resolved"] = _pick_first(item, "Ecpm", "ecpm", "ECPM") or 0
        item["coverage_rate_resolved"] = _to_percent(
            _pick_first(item, "Coverage", "coverage", "MatchRate", "matchRate")
        )
        item["click_rate_resolved"] = _to_percent(_pick_first(item, "Ctr", "ctr", "CTR"))
    return ad_data


def _resolve_leiyang_platform_label(item: dict[str, Any]) -> str:
    """广告位缺失时，用平台名/平台 ID 作为兜底单元标识。"""
    platform_name = str(_pick_first(item, "PlatformName", "platformName") or "").strip()
    if platform_name:
        return platform_name
    platform_id = _pick_first(item, "PlatformID", "platformId", "PlatformId")
    if platform_id is not None and str(platform_id).strip():
        return f"platform_{platform_id}"
    return ""


def _shape_leiyang_country_rows(rows: list[Any]) -> list[Any]:
    """国家维度：去掉广告位，整批按 country 入库。"""
    shaped: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row["ad_unit_resolved"] = ""
        shaped.append(row)
    return shaped


def _shape_leiyang_unit_rows(rows: list[Any]) -> list[Any]:
    """
    广告单元维度：去掉国家，补齐缺失 ad_unit，整批按 unit 入库。

    上游 ad-unit 接口偶发空 AdUnitName，用 PlatformName/PlatformID 兜底。
    """
    kept: list[Any] = []
    fallback_count = 0
    dropped = 0
    for row in rows:
        if not isinstance(row, dict):
            dropped += 1
            continue
        row["country_resolved"] = ""
        ad_unit = str(row.get("ad_unit_resolved") or "").strip()
        if not ad_unit:
            ad_unit = _resolve_leiyang_platform_label(row)
            if ad_unit:
                row["ad_unit_resolved"] = ad_unit
                fallback_count += 1
        if not str(row.get("ad_unit_resolved") or "").strip():
            dropped += 1
            continue
        kept.append(row)
    if fallback_count:
        logger.info(
            "LeiYang ad-unit 广告位兜底：%d 行使用 PlatformName/PlatformID 作为 ad_unit",
            fallback_count,
        )
    if dropped:
        logger.info(
            "LeiYang ad-unit 过滤：丢弃 %d 行（无广告位且无法兜底）",
            dropped,
        )
    return kept


def _shape_leiyang_daily_rows(rows: list[Any]) -> list[Any]:
    """日汇总维度：清除国家与广告位。"""
    shaped: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row["country_resolved"] = ""
        row["ad_unit_resolved"] = ""
        shaped.append(row)
    return shaped


def make_leiyang_preprocess(dimension: str):
    """按请求接口维度整理字段形态（report_type 由入库时显式指定）。"""

    def _transform(ad_data: list[Any]) -> list[Any]:
        rows = preprocess_leiyang_rows(ad_data)
        if dimension == REPORT_TYPE_COUNTRY:
            return _shape_leiyang_country_rows(rows)
        if dimension == REPORT_TYPE_UNIT:
            return _shape_leiyang_unit_rows(rows)
        if dimension == REPORT_TYPE_DAILY:
            return _shape_leiyang_daily_rows(rows)
        return rows

    return _transform


async def leiyang_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """LeiYang 定时拉数：按配置维度拉取报表并去重入库。"""
    base_url = settings.LEIYANG_API_BASE_URL
    api_key = settings.LEIYANG_API_KEY

    if not api_key or not api_key.strip():
        skip_msg = "跳过: LeiYang API 未配置（请在 .env 设置 LEIYANG_API_KEY）"
        logger.warning(skip_msg)
        set_task_result(LEIYANG_API_TASK_NAME, skip_msg)
        return

    ly_start, ly_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_params = {"起始日期": ly_start, "终止日期": ly_end}

    enabled_reports = [r for r in _LEIYANG_REPORTS if _is_report_enabled(r["env_flag"])]
    if not enabled_reports:
        skip_msg = (
            "跳过: LeiYang 未开启任何报表维度"
            "（LEIYANG_API_FETCH_COUNTRY / UNIT / DAILY 均为 false）"
        )
        logger.warning(skip_msg)
        set_task_result(LEIYANG_API_TASK_NAME, skip_msg)
        return

    summaries: list[str] = []
    transient_errors: list[str] = []
    hard_errors: list[str] = []

    for report in enabled_reports:
        report_label = report["label"]
        try:
            async def _make_fetch(p=report["path"], lb=report_label):
                return await fetch_leiyang_rows(
                    base_url=base_url,
                    api_key=api_key,
                    start=ly_start,
                    end=ly_end,
                    path=p,
                    label=lb,
                    limit=settings.LEIYANG_API_PAGE_SIZE,
                )

            outcome = await run_upstream_import_task(
                LEIYANG_API_TASK_NAME,
                credentials=None,
                fetch_data=_make_fetch,
                field_mapping=report["mapping"],
                source="LeiYang定时任务",
                notify_title=f"LeiYang ({report_label.split()[-1]})",
                data_transform=make_leiyang_preprocess(report["dimension"]),
                data_source=DATA_SOURCE_LEIYANG,
                report_type=report["report_type"],
                log_label=report_label,
                notify_params=notify_params,
            )
            if outcome == UpstreamTaskOutcome.SUCCESS:
                summaries.append(f"{report_label}: 成功")
            elif outcome == UpstreamTaskOutcome.SKIPPED_TRANSIENT:
                transient_errors.append(f"{report_label}: 上游暂时不可达")
            else:
                transient_errors.append(f"{report_label}: 已跳过({outcome.value})")
        except UpstreamTransientError as exc:
            transient_errors.append(f"{report_label}: 上游暂时不可达")
            logger.warning("LeiYang 报表瞬时故障 - %s: %s", report_label, exc)
        except Exception as exc:
            err = f"{report_label}: {exc}"
            hard_errors.append(err)
            logger.error("LeiYang 报表拉数失败 - %s", err)

    if hard_errors and not summaries and not transient_errors:
        msg = f"执行失败: {'; '.join(hard_errors)}"
        set_task_result(LEIYANG_API_TASK_NAME, msg)
        raise RuntimeError(msg)

    if hard_errors:
        msg = (
            f"部分失败: {'; '.join(hard_errors)}"
            + (f" | 软跳过: {'; '.join(transient_errors)}" if transient_errors else "")
            + (f" | 成功: {'; '.join(summaries)}" if summaries else "")
        )
        set_task_result(LEIYANG_API_TASK_NAME, msg)
        raise RuntimeError(msg)

    if transient_errors and not summaries:
        soft_msg = f"软跳过: 上游暂时不可达，等待下次调度 | {'; '.join(transient_errors)}"
        logger.warning("[%s] %s", LEIYANG_API_TASK_NAME, soft_msg)
        log_scheduled_task_skip(
            LEIYANG_API_TASK_NAME, "上游网络瞬时故障", detail="; ".join(transient_errors)
        )
        set_task_result(LEIYANG_API_TASK_NAME, soft_msg)
        return

    if transient_errors and summaries:
        msg = (
            f"部分跳过(上游暂时不可达): {'; '.join(transient_errors)} "
            f"| 成功: {'; '.join(summaries)}"
        )
        logger.warning("[%s] %s", LEIYANG_API_TASK_NAME, msg)
        set_task_result(LEIYANG_API_TASK_NAME, msg)
        return

    set_task_result(LEIYANG_API_TASK_NAME, "执行成功: " + "; ".join(summaries))
