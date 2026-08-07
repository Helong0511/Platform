"""
zhisuo 上游广告数据拉取定时任务。

- 按账号拉取 tecnee channel*：优先 data（国家+广告单元交叉），次之 country，可选 unit / daily 兜底
- 写入 data_source / report_type / upstream_account 元数据
- 当某日某产品细粒度均无数据时，可用 channeldaily 日报兜底
- 瞬时网络故障：已成功维度保留入库，不整段丢弃
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.ad_data_metadata import DATA_SOURCE_ZHISUO
from app.core.config import settings
from app.scheduler_module.task_names import ZHISUO_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    get_current_time_str,
    log_scheduled_task_skip,
    log_task_start,
    resolve_upstream_date_range,
    truncate_task_error_message,
)
from app.scheduler_module.upstream_fetch import (
    fetch_zhisuo_country_rows,
    fetch_zhisuo_daily_rows,
    fetch_zhisuo_data_rows,
    fetch_zhisuo_unit_rows,
)
from app.scheduler_module.upstream_http import UpstreamTransientError
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

# 国家+广告单元交叉（channeldata）
ZHISUO_DATA_FIELD_MAPPING = {
    "date": "date",
    "ad_unit": "ad_unit_name",
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


def _account_has_any_fetch(account: dict[str, Any]) -> bool:
    return bool(
        account.get("fetch_unit")
        or account.get("fetch_country")
        or account.get("fetch_data")
        or account.get("fetch_daily_fallback")
    )


def _is_zhisuo_account_config_error(exc: BaseException) -> bool:
    """上游凭证/账号配置类错误（如无效 clientId）：应跳过该账号并继续其它账号。"""
    text = str(exc).lower()
    markers = (
        "无效的clientid",
        "invalid clientid",
        "invalid client id",
        "invalid client_id",
    )
    return any(m in text for m in markers)


async def _import_zhisuo_account(
    account: dict[str, Any],
    *,
    base_url: str,
    start: str,
    end: str,
    current_time_str: str,
) -> tuple[list[str], Optional[UpstreamTransientError]]:
    """
    单账号：按维度边拉边入库。

    某维度瞬时故障时：已成功维度保留入库；停止后续维度请求；
    返回 (摘要列表, 瞬时异常或 None)。
    """
    client_id = str(account["client_id"])
    api_key = str(account["api_key"])
    summaries: list[str] = []
    transient: Optional[UpstreamTransientError] = None
    covered: set[tuple[str, str]] = set()
    notify_base = {"起始日期": start, "终止日期": end, "账号": client_id}

    async def _fetch_import_dimension(
        *,
        enabled: bool,
        key: str,
        fetch_factory,
        field_mapping: dict[str, str],
        source: str,
        notify_title: str,
        rows_to_covered: bool = True,
        transform_rows=None,
    ) -> None:
        nonlocal transient, covered
        if not enabled:
            return
        if transient is not None:
            summaries.append(f"{key}: 跳过(上游不可达)")
            return
        try:
            result = await fetch_factory()
            rows = list(result.rows)
            if transform_rows is not None:
                rows = transform_rows(rows)
            logger.info("ZhiSuo %s 账号 %s 拉取 %d 条", key, client_id, len(rows))
            if rows_to_covered:
                covered |= _zhisuo_product_date_keys(rows)
            if not rows:
                return
            summary = await import_upstream_ad_data(
                task_name=ZHISUO_API_TASK_NAME,
                data=rows,
                field_mapping=field_mapping,
                source=source,
                current_time_str=current_time_str,
                notify_title=notify_title,
                update_task_result=False,
                notify_params={**notify_base},
                data_source=DATA_SOURCE_ZHISUO,
                upstream_account=client_id,
            )
            summaries.append(f"{key}: {summary}")
        except UpstreamTransientError as e:
            transient = e
            summaries.append(f"{key}: 软跳过")
            logger.warning(
                "ZhiSuo %s 账号 %s 上游瞬时故障，保留已入库维度: %s",
                key,
                client_id,
                e,
            )

    await _fetch_import_dimension(
        enabled=bool(account.get("fetch_data")),
        key="data",
        fetch_factory=lambda: fetch_zhisuo_data_rows(
            base_url=base_url,
            client_id=client_id,
            api_key=api_key,
            start=start,
            end=end,
        ),
        field_mapping=ZHISUO_DATA_FIELD_MAPPING,
        source="ZhiSuo定时任务-国家+广告单元",
        notify_title=f"ZhiSuo-{client_id}-国家+广告单元",
    )

    # 国家：与交叉同时开启时，仅补交叉未覆盖的产品+日（次之）
    def _country_rows(rows: list[Any]) -> list[Any]:
        if not account.get("fetch_data"):
            return rows
        filtered = _daily_fallback_rows(rows, covered)
        if filtered:
            logger.info(
                "ZhiSuo 国家次级 账号 %s: %d 行（交叉已覆盖 %d 个产品+日）",
                client_id,
                len(filtered),
                len(covered),
            )
        return filtered

    await _fetch_import_dimension(
        enabled=bool(account.get("fetch_country")),
        key="country",
        fetch_factory=lambda: fetch_zhisuo_country_rows(
            base_url=base_url,
            client_id=client_id,
            api_key=api_key,
            start=start,
            end=end,
        ),
        field_mapping=ZHISUO_COUNTRY_FIELD_MAPPING,
        source="ZhiSuo定时任务-国家报告",
        notify_title=f"ZhiSuo-{client_id}-国家报告",
        transform_rows=_country_rows,
    )
    await _fetch_import_dimension(
        enabled=bool(account.get("fetch_unit")),
        key="unit",
        fetch_factory=lambda: fetch_zhisuo_unit_rows(
            base_url=base_url,
            client_id=client_id,
            api_key=api_key,
            start=start,
            end=end,
        ),
        field_mapping=ZHISUO_UNIT_FIELD_MAPPING,
        source="ZhiSuo定时任务-广告单元",
        notify_title=f"ZhiSuo-{client_id}-广告单元",
    )

    if account.get("fetch_daily_fallback") and transient is None:

        def _fallback_only(rows: list[Any]) -> list[Any]:
            filtered = _daily_fallback_rows(rows, covered)
            if filtered:
                logger.info(
                    "ZhiSuo 日报兜底 账号 %s: %d 行（已覆盖 %d 个产品+日）",
                    client_id,
                    len(filtered),
                    len(covered),
                )
            return filtered

        await _fetch_import_dimension(
            enabled=True,
            key="daily",
            fetch_factory=lambda: fetch_zhisuo_daily_rows(
                base_url=base_url,
                client_id=client_id,
                api_key=api_key,
                start=start,
                end=end,
            ),
            field_mapping=ZHISUO_DAILY_FIELD_MAPPING,
            source="ZhiSuo定时任务-日报兜底",
            notify_title=f"ZhiSuo-{client_id}-日报兜底",
            rows_to_covered=False,
            transform_rows=_fallback_only,
        )
    elif account.get("fetch_daily_fallback") and transient is not None:
        summaries.append("daily: 跳过(上游不可达)")

    if not summaries:
        summaries.append("无数据")
    return summaries, transient


async def zhisuo_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """zhisuo 定时拉数：按账号、按天拉取并写入带来源/维度的 ad_data。"""
    accounts = settings.get_zhisuo_accounts()
    base_url = settings.ZHISUO_API_BASE_URL

    if not accounts:
        msg = (
            "跳过: ZhiSuo API 未配置（请在 .env 设置 ZHISUO_API_CLIENT_ID / ZHISUO_API_KEY，"
            "或 ZHISUO_API_CLIENT_ID_2~5 / ZHISUO_API_KEY_2~5，或 ZHISUO_API_ACCOUNTS）"
        )
        logger.warning(msg)
        set_task_result(ZHISUO_API_TASK_NAME, msg)
        return

    active = [acc for acc in accounts if _account_has_any_fetch(acc)]
    if not active:
        msg = (
            "跳过: 所有 ZhiSuo 账号均未启用广告单元、国家、交叉或日报兜底拉数"
            "（请检查 ZHISUO_API_FETCH_UNIT / ZHISUO_API_FETCH_COUNTRY / "
            "ZHISUO_API_FETCH_DATA / ZHISUO_API_FETCH_DAILY_FALLBACK / ZHISUO_API_ACCOUNT_FETCH）"
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
    invalid_accounts: list[str] = []
    try:
        for account in active:
            client_id = str(account["client_id"])
            try:
                parts, transient = await _import_zhisuo_account(
                    account,
                    base_url=base_url,
                    start=zhisuo_start,
                    end=zhisuo_end,
                    current_time_str=current_time_str,
                )
            except Exception as e:
                if _is_zhisuo_account_config_error(e):
                    invalid_accounts.append(client_id)
                    phase_summaries.append(f"{client_id}[跳过:无效凭证]")
                    logger.warning(
                        "[%s] 账号 %s 凭证无效，跳过并继续其它账号: %s",
                        ZHISUO_API_TASK_NAME,
                        client_id,
                        truncate_task_error_message(str(e)),
                    )
                    continue
                raise
            phase_summaries.append(f"{client_id}[{'; '.join(parts)}]")
            if transient is not None:
                prefix = f"部分成功: {'; '.join(phase_summaries)} | "
                soft_msg = f"{prefix}软跳过: 上游暂时不可达，等待下次调度 | {transient}"
                logger.warning("[%s] %s", ZHISUO_API_TASK_NAME, soft_msg)
                log_scheduled_task_skip(
                    ZHISUO_API_TASK_NAME, "上游网络瞬时故障", detail=str(transient)
                )
                set_task_result(ZHISUO_API_TASK_NAME, soft_msg)
                return

        joined = "; ".join(phase_summaries)
        if invalid_accounts and len(invalid_accounts) == len(active):
            skip_msg = (
                f"跳过: 全部账号凭证无效（{', '.join(invalid_accounts)}），"
                f"请检查 ZHISUO_API_CLIENT_ID / KEY | {joined}"
            )
            logger.warning("[%s] %s", ZHISUO_API_TASK_NAME, skip_msg)
            log_scheduled_task_skip(
                ZHISUO_API_TASK_NAME,
                "账号凭证无效",
                detail=", ".join(invalid_accounts),
            )
            set_task_result(ZHISUO_API_TASK_NAME, skip_msg)
            return

        if invalid_accounts:
            set_task_result(
                ZHISUO_API_TASK_NAME,
                f"部分成功(已跳过无效账号 {', '.join(invalid_accounts)}): {joined}",
            )
        else:
            set_task_result(ZHISUO_API_TASK_NAME, f"执行成功: {joined}")
    except Exception as e:
        error_detail = truncate_task_error_message(str(e))
        # 不带 exc_info，避免与调度器失败日志重复触发 Telegram
        logger.error("%s 执行失败: %s", ZHISUO_API_TASK_NAME, error_detail)
        set_task_result(ZHISUO_API_TASK_NAME, error_detail)
        raise
