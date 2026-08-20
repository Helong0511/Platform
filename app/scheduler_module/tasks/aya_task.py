"""
Aya / AB Data 上游广告数据拉取定时任务。

支持三种报表维度（参见 tests/API/ab_data_API文档(1).pdf）：
- 日报 getDay
- 国家 getAdsDataCountry（默认开启）
- 广告单元 getAdsDataUnit

cpName 作为 upstream_account 写入，便于区分上游账号/公司名。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from app.core.ad_data_metadata import (
    DATA_SOURCE_AYA,
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_DAILY,
    REPORT_TYPE_UNIT,
)
from app.core.config import settings
from app.scheduler_module.task_names import AYA_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    get_current_time_str,
    log_scheduled_task_skip,
    log_task_start,
    resolve_upstream_date_range,
    truncate_task_error_message,
)
from app.scheduler_module.upstream_fetch import (
    AYA_PATH_COUNTRY,
    AYA_PATH_DAILY,
    AYA_PATH_UNIT,
    fetch_aya_rows,
)
from app.scheduler_module.upstream_http import UpstreamTransientError
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

AYA_COMMON_FIELD_MAPPING = {
    "date": "datetime",
    "product_name": "productName",
    "request_count": "adRequests",
    "match_count": "matchedRequests",
    "display_count": "viewsCount",
    "click_count": "clickCount",
    "coverage_rate": "coverage",
    "revenue_before_deduct": "channelEstimatedIncome",
    "click_rate": "ctr",
    "cpc": "channelCpc",
    "ecpm_before_deduct": "channelEcpm",
}

AYA_COUNTRY_FIELD_MAPPING = {
    **AYA_COMMON_FIELD_MAPPING,
    "country_code": "country",
}

AYA_UNIT_FIELD_MAPPING = {
    **AYA_COMMON_FIELD_MAPPING,
    "ad_unit": "ad_unit_resolved",
}

AYA_DAILY_FIELD_MAPPING = dict(AYA_COMMON_FIELD_MAPPING)


def _group_rows_by_cp_name(rows: list[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        cp_name = str(row.get("cpName") or "").strip() or "default"
        grouped[cp_name].append(row)
    return dict(grouped)


def preprocess_aya_unit_rows(ad_data: list[Any]) -> list[Any]:
    """广告单元维度：优先 unit，其次 paymentName。"""
    for item in ad_data:
        unit = str(item.get("unit") or "").strip()
        payment = str(item.get("paymentName") or "").strip()
        item["ad_unit_resolved"] = unit or payment
    return ad_data


async def _import_aya_dimension(
    *,
    rows: list[Any],
    field_mapping: dict[str, str],
    source: str,
    notify_title: str,
    current_time_str: str,
    notify_base: dict[str, str],
    report_type: str,
    data_transform=None,
) -> list[str]:
    if not rows:
        return []
    summaries: list[str] = []
    for cp_name, group_rows in _group_rows_by_cp_name(rows).items():
        summary = await import_upstream_ad_data(
            task_name=AYA_API_TASK_NAME,
            data=group_rows,
            field_mapping=field_mapping,
            source=source,
            current_time_str=current_time_str,
            notify_title=f"{notify_title}-{cp_name}",
            update_task_result=False,
            notify_params={**notify_base, "账号": cp_name},
            data_source=DATA_SOURCE_AYA,
            upstream_account=cp_name,
            report_type=report_type,
            data_transform=data_transform,
        )
        summaries.append(f"{cp_name}: {summary}")
    return summaries


async def aya_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Aya 定时拉数：按配置拉取日报/国家/广告单元并入库。"""
    secret_key = settings.AYA_API_SECRET_KEY
    base_url = settings.AYA_API_BASE_URL
    fetch_daily = settings.AYA_API_FETCH_DAILY
    fetch_country = settings.AYA_API_FETCH_COUNTRY
    fetch_unit = settings.AYA_API_FETCH_UNIT

    if not secret_key.strip():
        msg = "跳过: Aya API 未配置（请在 .env 设置 AYA_API_SECRET_KEY）"
        logger.warning(msg)
        set_task_result(AYA_API_TASK_NAME, msg)
        return

    if not (fetch_daily or fetch_country or fetch_unit):
        msg = (
            "跳过: Aya 未启用任何报表维度"
            "（请检查 AYA_API_FETCH_DAILY / AYA_API_FETCH_COUNTRY / AYA_API_FETCH_UNIT）"
        )
        logger.warning(msg)
        set_task_result(AYA_API_TASK_NAME, msg)
        return

    aya_start, aya_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_base = {"起始日期": aya_start, "终止日期": aya_end}
    current_time_str = get_current_time_str()
    log_task_start(AYA_API_TASK_NAME)

    phase_summaries: list[str] = []
    dim_errors: list[str] = []
    dim_soft_skips: list[str] = []

    # ---- 日报维度（独立 try/except） ----
    if fetch_daily:
        try:
            daily_result = await fetch_aya_rows(
                base_url=base_url,
                secret_key=secret_key,
                start=aya_start,
                end=aya_end,
                path=AYA_PATH_DAILY,
                label="Aya 日报 API",
            )
            daily_rows = list(daily_result.rows)
            logger.info("Aya 日报拉取 %d 条", len(daily_rows))
            daily_parts = await _import_aya_dimension(
                rows=daily_rows,
                field_mapping=AYA_DAILY_FIELD_MAPPING,
                source="Aya定时任务-日报",
                notify_title="Aya-日报",
                current_time_str=current_time_str,
                notify_base=notify_base,
                report_type=REPORT_TYPE_DAILY,
            )
            phase_summaries.append(
                "daily[" + ("; ".join(daily_parts) if daily_parts else "无数据") + "]"
            )
        except UpstreamTransientError as e:
            dim_soft_skips.append(f"daily: {e}")
            logger.warning("Aya 日报维度软跳过: %s", e)
        except Exception as e:
            detail = truncate_task_error_message(str(e))
            dim_errors.append(f"daily: {detail}")
            logger.error("Aya 日报维度失败: %s", detail)

    # ---- 国家维度（独立 try/except） ----
    if fetch_country:
        try:
            country_result = await fetch_aya_rows(
                base_url=base_url,
                secret_key=secret_key,
                start=aya_start,
                end=aya_end,
                path=AYA_PATH_COUNTRY,
                label="Aya 国家 API",
            )
            country_rows = list(country_result.rows)
            logger.info("Aya 国家拉取 %d 条", len(country_rows))
            country_parts = await _import_aya_dimension(
                rows=country_rows,
                field_mapping=AYA_COUNTRY_FIELD_MAPPING,
                source="Aya定时任务-国家",
                notify_title="Aya-国家",
                current_time_str=current_time_str,
                notify_base=notify_base,
                report_type=REPORT_TYPE_COUNTRY,
            )
            phase_summaries.append(
                "country[" + ("; ".join(country_parts) if country_parts else "无数据") + "]"
            )
        except UpstreamTransientError as e:
            dim_soft_skips.append(f"country: {e}")
            logger.warning("Aya 国家维度软跳过: %s", e)
        except Exception as e:
            detail = truncate_task_error_message(str(e))
            dim_errors.append(f"country: {detail}")
            logger.error("Aya 国家维度失败: %s", detail)

    # ---- 广告单元维度（独立 try/except） ----
    if fetch_unit:
        try:
            unit_result = await fetch_aya_rows(
                base_url=base_url,
                secret_key=secret_key,
                start=aya_start,
                end=aya_end,
                path=AYA_PATH_UNIT,
                label="Aya 广告单元 API",
            )
            unit_rows = list(unit_result.rows)
            logger.info("Aya 广告单元拉取 %d 条", len(unit_rows))
            unit_parts = await _import_aya_dimension(
                rows=unit_rows,
                field_mapping=AYA_UNIT_FIELD_MAPPING,
                source="Aya定时任务-广告单元",
                notify_title="Aya-广告单元",
                current_time_str=current_time_str,
                notify_base=notify_base,
                report_type=REPORT_TYPE_UNIT,
                data_transform=preprocess_aya_unit_rows,
            )
            phase_summaries.append(
                "unit[" + ("; ".join(unit_parts) if unit_parts else "无数据") + "]"
            )
        except UpstreamTransientError as e:
            dim_soft_skips.append(f"unit: {e}")
            logger.warning("Aya 广告单元维度软跳过: %s", e)
        except Exception as e:
            detail = truncate_task_error_message(str(e))
            dim_errors.append(f"unit: {detail}")
            logger.error("Aya 广告单元维度失败: %s", detail)

    # ---- 汇总处理 ----
    if phase_summaries and not dim_errors:
        # 全部成功（可能有部分软跳过）
        if dim_soft_skips:
            soft_msg = (
                f"部分成功: {'; '.join(phase_summaries)} | "
                f"软跳过: {'; '.join(dim_soft_skips)}"
            )
            logger.warning("[%s] %s", AYA_API_TASK_NAME, soft_msg)
            log_scheduled_task_skip(AYA_API_TASK_NAME, "部分维度上游网络瞬时故障")
            set_task_result(AYA_API_TASK_NAME, soft_msg)
        else:
            set_task_result(
                AYA_API_TASK_NAME,
                "执行成功: " + "; ".join(phase_summaries),
            )
    elif phase_summaries and dim_errors:
        # 部分成功 + 部分硬错误
        msg = (
            f"部分成功: {'; '.join(phase_summaries)} | "
            f"失败: {'; '.join(dim_errors)}"
        )
        logger.error("[%s] %s", AYA_API_TASK_NAME, msg)
        set_task_result(AYA_API_TASK_NAME, msg)
        raise RuntimeError(msg)
    elif dim_soft_skips and not dim_errors:
        # 全部为软跳过（无成功数据）
        soft_msg = f"全部软跳过: {'; '.join(dim_soft_skips)}"
        logger.warning("[%s] %s", AYA_API_TASK_NAME, soft_msg)
        log_scheduled_task_skip(AYA_API_TASK_NAME, "上游网络瞬时故障", detail=str(dim_soft_skips))
        set_task_result(AYA_API_TASK_NAME, soft_msg)
    elif dim_errors:
        msg = f"全部失败: {'; '.join(dim_errors)}"
        logger.error("[%s] %s", AYA_API_TASK_NAME, msg)
        set_task_result(AYA_API_TASK_NAME, msg)
        raise RuntimeError(msg)
