"""
zhisuo 上游广告数据拉取定时任务。

功能说明：
- 从 zhisuo API 获取广告单元 / 国家报告数据，检查重复后插入 ad_data
- 每个账号可单独配置 fetch_unit / fetch_country（见 ZHISUO_API_ACCOUNT_FETCH）
- 国家报告返回英文国名（如 United States），入库时由 process_api_ad_data 转为 ISO 二字母代码
- 国家报告与广告单元报告分别入库（纯国家 / 纯广告单元行）；每日汇总按
  build_daily_summary_dimension_filter 互斥选源，避免 fetch_unit+fetch_country 双开时重复计数。
- 支持多账号顺序拉取后合并入库
"""
import logging
from collections.abc import Awaitable, Callable
from typing import Any

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
    UpstreamFetchResult,
    UpstreamFetchStats,
    fetch_zhisuo_country_rows,
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

# country 字段为英文国名，process_api_ad_data 会调用 find_country_code_by_any_format 转为 US 等
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


def _filter_accounts_for_report(
    accounts: list[dict[str, Any]],
    *,
    report: str,
) -> list[dict[str, Any]]:
    """按报告类型筛选启用了对应开关的账号。"""
    flag_key = "fetch_unit" if report == "unit" else "fetch_country"
    return [acc for acc in accounts if acc.get(flag_key)]


async def _fetch_zhisuo_rows_for_accounts(
    fetch_fn: Callable[..., Awaitable[UpstreamFetchResult]],
    *,
    base_url: str,
    accounts: list[dict[str, Any]],
    start: str,
    end: str,
    report_label: str,
) -> UpstreamFetchResult:
    """多账号顺序拉取并合并行列表与分页统计。"""
    if not accounts:
        return UpstreamFetchResult(rows=[], stats=UpstreamFetchStats())

    all_data: list[Any] = []
    stats_list: list[UpstreamFetchStats] = []
    fetch_errors: list[str] = []
    for acc in accounts:
        client_id = str(acc["client_id"])
        try:
            result = await fetch_fn(
                base_url=base_url,
                client_id=client_id,
                api_key=str(acc["api_key"]),
                start=start,
                end=end,
            )
            all_data.extend(result.rows)
            stats_list.append(result.stats)
            logger.info(
                "Zhisuo %s 账号 %s 拉取 %d 条（%d/%s 页）",
                report_label,
                client_id,
                result.stats.rows_fetched,
                result.stats.pages_fetched,
                result.stats.total_pages or "?",
            )
        except Exception as e:
            err_msg = f"{report_label} 账号 {client_id}: {e}"
            fetch_errors.append(err_msg)
            logger.error("Zhisuo 拉取失败 - %s", err_msg, exc_info=True)

    if fetch_errors and not all_data:
        raise Exception(f"所有 Zhisuo {report_label} 拉取失败: " + "; ".join(fetch_errors))
    if fetch_errors:
        logger.warning("部分 Zhisuo %s 拉取失败: %s", report_label, "; ".join(fetch_errors))
    return UpstreamFetchResult(
        rows=all_data,
        stats=UpstreamFetchStats.merge(*stats_list) if stats_list else UpstreamFetchStats(),
    )


async def zhisuo_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """zhisuo 定时拉数：按账号开关拉取广告单元 / 国家报告并分别入库。"""
    accounts = settings.get_zhisuo_accounts()
    base_url = settings.ZHISUO_API_BASE_URL
    unit_accounts = _filter_accounts_for_report(accounts, report="unit")
    country_accounts = _filter_accounts_for_report(accounts, report="country")

    if not accounts:
        msg = (
            "跳过: Zhisuo API 未配置（请在 .env 设置 ZHISUO_API_CLIENT_ID / ZHISUO_API_KEY，"
            "或 ZHISUO_API_CLIENT_ID_2~4 / ZHISUO_API_KEY_2~4，或 ZHISUO_API_ACCOUNTS）"
        )
        logger.warning(msg)
        set_task_result(ZHISUO_API_TASK_NAME, msg)
        return

    if not unit_accounts and not country_accounts:
        msg = (
            "跳过: 所有 Zhisuo 账号均未启用广告单元或国家报告拉数"
            "（请检查 ZHISUO_API_FETCH_UNIT / ZHISUO_API_FETCH_COUNTRY / ZHISUO_API_ACCOUNT_FETCH）"
        )
        logger.warning(msg)
        set_task_result(ZHISUO_API_TASK_NAME, msg)
        return

    for acc in accounts:
        logger.debug(
            "Zhisuo 账号 %s 拉数开关: 广告单元=%s, 国家报告=%s",
            acc["client_id"],
            acc.get("fetch_unit"),
            acc.get("fetch_country"),
        )

    zhisuo_start, zhisuo_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )

    current_time_str = get_current_time_str()
    log_task_start(ZHISUO_API_TASK_NAME)

    phase_summaries: list[str] = []
    try:
        if unit_accounts:
            unit_result = await _fetch_zhisuo_rows_for_accounts(
                fetch_zhisuo_unit_rows,
                base_url=base_url,
                accounts=unit_accounts,
                start=zhisuo_start,
                end=zhisuo_end,
                report_label="广告单元",
            )
            unit_summary = await import_upstream_ad_data(
                task_name=ZHISUO_API_TASK_NAME,
                data=unit_result.rows,
                field_mapping=ZHISUO_UNIT_FIELD_MAPPING,
                source="zhisuo定时任务-广告单元",
                current_time_str=current_time_str,
                notify_title="zhisuo-广告单元",
                update_task_result=False,
                notify_params={
                    "起始日期": zhisuo_start,
                    "终止日期": zhisuo_end,
                    "账号": ",".join(str(a["client_id"]) for a in unit_accounts),
                },
                fetch_stats=unit_result.stats,
            )
            unit_ids = ",".join(str(a["client_id"]) for a in unit_accounts)
            phase_summaries.append(f"广告单元[{unit_ids}]: {unit_summary}")

        if country_accounts:
            country_result = await _fetch_zhisuo_rows_for_accounts(
                fetch_zhisuo_country_rows,
                base_url=base_url,
                accounts=country_accounts,
                start=zhisuo_start,
                end=zhisuo_end,
                report_label="国家报告",
            )
            country_summary = await import_upstream_ad_data(
                task_name=ZHISUO_API_TASK_NAME,
                data=country_result.rows,
                field_mapping=ZHISUO_COUNTRY_FIELD_MAPPING,
                source="zhisuo定时任务-国家报告",
                current_time_str=current_time_str,
                notify_title="zhisuo-国家报告",
                update_task_result=False,
                notify_params={
                    "起始日期": zhisuo_start,
                    "终止日期": zhisuo_end,
                    "账号": ",".join(str(a["client_id"]) for a in country_accounts),
                },
                fetch_stats=country_result.stats,
            )
            country_ids = ",".join(str(a["client_id"]) for a in country_accounts)
            phase_summaries.append(f"国家报告[{country_ids}]: {country_summary}")

        set_task_result(
            ZHISUO_API_TASK_NAME,
            "执行成功: " + "; ".join(phase_summaries),
        )
    except Exception as e:
        error_detail = truncate_task_error_message(str(e))
        logger.error(f"{ZHISUO_API_TASK_NAME} 执行失败: {error_detail}", exc_info=True)
        logger.warning(f"[zhisuo] {ZHISUO_API_TASK_NAME} 执行失败: {error_detail}")
        set_task_result(ZHISUO_API_TASK_NAME, error_detail)
        raise
