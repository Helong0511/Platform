"""
zhisuo 上游广告数据拉取定时任务。

- 按天循环拉取 unit/country，避免区间查询漏数
- 写入 data_source / report_type / upstream_account 元数据
- 当某日某产品 unit+country 均无数据时，用 channeldaily 日报兜底
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.ad_data_metadata import (
    DATA_SOURCE_ZHISUO,
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_DAILY,
    REPORT_TYPE_UNIT,
)
from app.core.config import settings
from app.scheduler_module.task_names import ZHISUO_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    get_current_time_str,
    log_task_start,
    resolve_upstream_date_range,
    truncate_task_error_message,
)
from app.scheduler_module.upstream_fetch import (
    fetch_zhisuo_country_rows,
    fetch_zhisuo_daily_rows,
    fetch_zhisuo_unit_rows,
)
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

ZHISUO_UNIT_FIELD_MAPPING = {
    "date": "date",
    "ad_unit": "ad_unit_name",
    "product_name": "domain_name",
    "request_count": "ad_requests",
    "match_count": "matched_requests",
    "display_count": "ad_impressions",
    "click_count": "clicks",
    "revenue_before_deduct": "estimated_earnings",
    "ecpm_before_deduct": "ecpm",
    "coverage_rate": "coverage_rate",
    "display_rate": "display_rate",
    "click_rate": "click_through_rate",
    "cpc": "cpc",
}

ZHISUO_COUNTRY_FIELD_MAPPING = {
    "date": "date",
    "product_name": "domain_name",
    "country_code": "country",
    "request_count": "ad_requests",
    "match_count": "matched_requests",
    "display_count": "ad_impressions",
    "click_count": "clicks",
    "revenue_before_deduct": "estimated_earnings",
    "ecpm_before_deduct": "ecpm",
    "coverage_rate": "coverage_rate",
    "display_rate": "display_rate",
    "click_rate": "click_through_rate",
    "cpc": "cpc",
}

ZHISUO_DAILY_FIELD_MAPPING = {
    "date": "date",
    "product_name": "domain_name",
    "request_count": "ad_requests",
    "match_count": "matched_requests",
    "display_count": "ad_impressions",
    "click_count": "clicks",
    "revenue_before_deduct": "estimated_earnings",
    "ecpm_before_deduct": "ecpm",
    "coverage_rate": "coverage_rate",
    "display_rate": "display_rate",
    "click_rate": "click_through_rate",
    "cpc": "cpc",
}


def _zhisuo_product_date_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for row in rows:
        domain = str(row.get("domain_name") or "").strip()
        day = str(row.get("date") or "")[:10]
        if domain and day:
            keys.add((domain, day))
    return keys


def _daily_fallback_rows(
    daily_rows: list[Any],
    covered: set[tuple[str, str]],
) -> list[Any]:
    fallback: list[Any] = []
    for row in daily_rows:
        domain = str(row.get("domain_name") or "").strip()
        day = str(row.get("date") or "")[:10]
        if domain and day and (domain, day) not in covered:
            fallback.append(row)
    return fallback


async def _import_zhisuo_account(
    account: dict[str, Any],
    *,
    base_url: str,
    start: str,
    end: str,
    current_time_str: str,
) -> list[str]:
    """单账号：按天拉 unit/country，条件兜底 daily，分别入库。"""
    client_id = str(account["client_id"])
    api_key = str(account["api_key"])
    summaries: list[str] = []

    unit_rows: list[Any] = []
    if account.get("fetch_unit"):
        unit_result = await fetch_zhisuo_unit_rows(
            base_url=base_url,
            client_id=client_id,
            api_key=api_key,
            start=start,
            end=end,
        )
        unit_rows = list(unit_result.rows)
        logger.info("Zhisuo 广告单元 账号 %s 拉取 %d 条", client_id, len(unit_rows))

    country_rows: list[Any] = []
    if account.get("fetch_country"):
        country_result = await fetch_zhisuo_country_rows(
            base_url=base_url,
            client_id=client_id,
            api_key=api_key,
            start=start,
            end=end,
        )
        country_rows = list(country_result.rows)
        logger.info("Zhisuo 国家报告 账号 %s 拉取 %d 条", client_id, len(country_rows))

    covered = _zhisuo_product_date_keys(unit_rows) | _zhisuo_product_date_keys(country_rows)
    daily_fallback: list[Any] = []
    if account.get("fetch_daily_fallback"):
        daily_result = await fetch_zhisuo_daily_rows(
            base_url=base_url,
            client_id=client_id,
            api_key=api_key,
            start=start,
            end=end,
        )
        daily_fallback = _daily_fallback_rows(list(daily_result.rows), covered)
        if daily_fallback:
            logger.info(
                "Zhisuo 日报兜底 账号 %s: %d 行（已覆盖 %d 个产品+日）",
                client_id,
                len(daily_fallback),
                len(covered),
            )

    notify_base = {"起始日期": start, "终止日期": end, "账号": client_id}

    if unit_rows:
        unit_summary = await import_upstream_ad_data(
            task_name=ZHISUO_API_TASK_NAME,
            data=unit_rows,
            field_mapping=ZHISUO_UNIT_FIELD_MAPPING,
            source="zhisuo定时任务-广告单元",
            current_time_str=current_time_str,
            notify_title=f"zhisuo-{client_id}-广告单元",
            update_task_result=False,
            notify_params={**notify_base, "报表": "unit"},
            data_source=DATA_SOURCE_ZHISUO,
            report_type=REPORT_TYPE_UNIT,
            upstream_account=client_id,
        )
        summaries.append(f"unit: {unit_summary}")

    if country_rows:
        country_summary = await import_upstream_ad_data(
            task_name=ZHISUO_API_TASK_NAME,
            data=country_rows,
            field_mapping=ZHISUO_COUNTRY_FIELD_MAPPING,
            source="zhisuo定时任务-国家报告",
            current_time_str=current_time_str,
            notify_title=f"zhisuo-{client_id}-国家报告",
            update_task_result=False,
            notify_params={**notify_base, "报表": "country"},
            data_source=DATA_SOURCE_ZHISUO,
            report_type=REPORT_TYPE_COUNTRY,
            upstream_account=client_id,
        )
        summaries.append(f"country: {country_summary}")

    if daily_fallback:
        daily_summary = await import_upstream_ad_data(
            task_name=ZHISUO_API_TASK_NAME,
            data=daily_fallback,
            field_mapping=ZHISUO_DAILY_FIELD_MAPPING,
            source="zhisuo定时任务-日报兜底",
            current_time_str=current_time_str,
            notify_title=f"zhisuo-{client_id}-日报兜底",
            update_task_result=False,
            notify_params={**notify_base, "报表": "daily"},
            data_source=DATA_SOURCE_ZHISUO,
            report_type=REPORT_TYPE_DAILY,
            upstream_account=client_id,
        )
        summaries.append(f"daily: {daily_summary}")

    if not summaries:
        summaries.append("无数据")
    return summaries


async def zhisuo_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """zhisuo 定时拉数：按账号、按天拉取并写入带来源/维度的 ad_data。"""
    accounts = settings.get_zhisuo_accounts()
    base_url = settings.ZHISUO_API_BASE_URL

    if not accounts:
        msg = (
            "跳过: Zhisuo API 未配置（请在 .env 设置 ZHISUO_API_CLIENT_ID / ZHISUO_API_KEY，"
            "或 ZHISUO_API_CLIENT_ID_2~4 / ZHISUO_API_KEY_2~4，或 ZHISUO_API_ACCOUNTS）"
        )
        logger.warning(msg)
        set_task_result(ZHISUO_API_TASK_NAME, msg)
        return

    active = [
        acc for acc in accounts
        if acc.get("fetch_unit") or acc.get("fetch_country") or acc.get("fetch_daily_fallback")
    ]
    if not active:
        msg = (
            "跳过: 所有 Zhisuo 账号均未启用广告单元、国家报告或日报兜底拉数"
            "（请检查 ZHISUO_API_FETCH_UNIT / ZHISUO_API_FETCH_COUNTRY / "
            "ZHISUO_API_FETCH_DAILY_FALLBACK / ZHISUO_API_ACCOUNT_FETCH）"
        )
        logger.warning(msg)
        set_task_result(ZHISUO_API_TASK_NAME, msg)
        return

    zhisuo_start, zhisuo_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )

    current_time_str = get_current_time_str()
    log_task_start(ZHISUO_API_TASK_NAME)

    phase_summaries: list[str] = []
    try:
        for account in active:
            client_id = str(account["client_id"])
            parts = await _import_zhisuo_account(
                account,
                base_url=base_url,
                start=zhisuo_start,
                end=zhisuo_end,
                current_time_str=current_time_str,
            )
            phase_summaries.append(f"{client_id}[{'; '.join(parts)}]")

        set_task_result(
            ZHISUO_API_TASK_NAME,
            "执行成功: " + "; ".join(phase_summaries),
        )
    except Exception as e:
        error_detail = truncate_task_error_message(str(e))
        logger.error("%s 执行失败: %s", ZHISUO_API_TASK_NAME, error_detail, exc_info=True)
        set_task_result(ZHISUO_API_TASK_NAME, error_detail)
        raise
