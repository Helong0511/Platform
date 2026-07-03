"""
Google Ad Manager（GAM）定时拉数任务。

每小时拉取 ad_unit / country / site 报表到内存，
country 与 ad_unit 分形态入库；site 仅做一致性校验。
账号与白名单见项目 config/gam_scheduler.json。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from app.scheduler_module.gam_fetch import run_gam_fetch_to_memory
from app.scheduler_module.gam_import import import_gam_account_bundle
from app.scheduler_module.gam_scheduler_config import (
    gam_scheduler_config_exists,
    resolve_gam_scheduler_accounts,
)
from app.scheduler_module.task_names import GAM_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    get_current_time_str,
    log_scheduled_task_skip,
    log_task_start,
    resolve_upstream_date_range,
    truncate_task_error_message,
)

logger = logging.getLogger(__name__)

GAM_SKIP_NO_CONFIG = (
    "跳过: 未找到 config/gam_scheduler.json，请先配置 GAM 账号后再执行"
)
GAM_SKIP_NO_ACCOUNTS = "跳过: gam_scheduler.json 中未配置 GAM 账号"


async def google_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Google API 获取数据：内存拉数 + GAM 专用分报表入库。"""
    if not gam_scheduler_config_exists():
        logger.warning(GAM_SKIP_NO_CONFIG)
        log_scheduled_task_skip(
            GAM_API_TASK_NAME,
            "未配置 GAM 配置文件",
            detail=GAM_SKIP_NO_CONFIG,
        )
        set_task_result(GAM_API_TASK_NAME, GAM_SKIP_NO_CONFIG)
        return

    gam_accounts = resolve_gam_scheduler_accounts()
    if not gam_accounts:
        logger.warning(GAM_SKIP_NO_ACCOUNTS)
        log_scheduled_task_skip(
            GAM_API_TASK_NAME,
            "未配置 GAM 账号",
            detail=GAM_SKIP_NO_ACCOUNTS,
        )
        set_task_result(GAM_API_TASK_NAME, GAM_SKIP_NO_ACCOUNTS)
        return

    gam_start, gam_end = resolve_upstream_date_range(start_date, end_date)
    current_time_str = get_current_time_str()
    log_task_start(GAM_API_TASK_NAME)
    account_summaries = []
    for item in gam_accounts:
        key = str(item.get("key") or "?")
        report_keys = item.get("report_keys")
        if isinstance(report_keys, (list, tuple)):
            reports = ",".join(str(part) for part in report_keys)
        elif report_keys is None:
            reports = ""
        else:
            reports = str(report_keys)
        account_summaries.append(f"{key}[{reports}]")
    logger.info(
        "%s 使用 GAM 账号: %s",
        GAM_API_TASK_NAME,
        "; ".join(account_summaries),
    )

    try:
        bundles = await asyncio.to_thread(
            run_gam_fetch_to_memory,
            date.fromisoformat(gam_start),
            date.fromisoformat(gam_end),
            accounts=gam_accounts,
        )
    except Exception as exc:
        error_detail = truncate_task_error_message(str(exc))
        logger.error("%s 拉数失败: %s", GAM_API_TASK_NAME, error_detail, exc_info=True)
        set_task_result(GAM_API_TASK_NAME, error_detail)
        raise

    if not bundles:
        set_task_result(GAM_API_TASK_NAME, "执行成功: 暂无可用 GAM 账号数据")
        return

    phase_summaries: list[str] = []
    failures: list[str] = []
    for bundle in bundles:
        account_key = bundle.get("account_key", "?")
        try:
            summary = await import_gam_account_bundle(
                bundle,
                task_name=GAM_API_TASK_NAME,
                current_time_str=current_time_str,
            )
            phase_summaries.append(f"{account_key}: {summary}")
        except Exception as exc:
            err = f"{account_key}: {exc}"
            failures.append(err)
            logger.error("GAM 账号入库失败 - %s", err, exc_info=True)

    if failures and not phase_summaries:
        message = truncate_task_error_message("; ".join(failures))
        set_task_result(GAM_API_TASK_NAME, message)
        raise RuntimeError(message)

    result = "执行成功: " + "; ".join(phase_summaries)
    if failures:
        result += " | 部分失败: " + "; ".join(failures)
    set_task_result(GAM_API_TASK_NAME, truncate_task_error_message(result))
