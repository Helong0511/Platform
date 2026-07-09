"""
Google Ad Manager（GAM）定时拉数任务。

每小时拉取 ad_unit / country / site 报表到内存，
country 与 ad_unit 分形态入库；site 仅做一致性校验。
账号与白名单见项目 config/gam_scheduler.json。

容错约定：
- 单账号拉数失败时，失败原因须写入 scheduled_tasks.last_error，并计为任务失败（error_count）
- 其他账号仍可继续入库；结果摘要为「部分失败」而非「执行成功」
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


def _collect_fetch_failures(bundles: list[dict]) -> list[str]:
    """从拉数结果中收集带 fetch_error 的账号失败摘要。"""
    failures: list[str] = []
    for bundle in bundles:
        fetch_error = str(bundle.get("fetch_error") or "").strip()
        if not fetch_error:
            continue
        account_key = str(bundle.get("account_key") or "?")
        network_code = str(bundle.get("network_code") or "?")
        # fetch_error 已含中文说明；前缀账号便于管理端「最后错误」一眼定位
        if fetch_error.startswith(f"{account_key}("):
            failures.append(fetch_error)
        else:
            failures.append(f"{account_key}({network_code}): {fetch_error}")
    return failures


async def google_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """
    Google API 获取数据：内存拉数 + GAM 专用分报表入库。

    任一侧账号拉数或入库失败时抛出 RuntimeError，由调度器写入 last_error 并增加 error_count。
    """
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

    # ---------- 1. 拉数阶段已失败的账号（如 NO_NETWORKS_TO_ACCESS）----------
    fetch_failures = _collect_fetch_failures(bundles)
    phase_summaries: list[str] = []
    import_failures: list[str] = []

    # ---------- 2. 仅对拉数成功的账号入库 ----------
    for bundle in bundles:
        account_key = bundle.get("account_key", "?")
        if bundle.get("fetch_error"):
            continue
        try:
            summary = await import_gam_account_bundle(
                bundle,
                task_name=GAM_API_TASK_NAME,
                current_time_str=current_time_str,
            )
            phase_summaries.append(f"{account_key}: {summary}")
        except Exception as exc:
            err = f"{account_key}: {exc}"
            import_failures.append(err)
            logger.error("GAM 账号入库失败 - %s", err, exc_info=True)

    all_failures = fetch_failures + import_failures

    # 全部账号失败：明确失败文案，调度器记 error_count
    if all_failures and not phase_summaries:
        message = truncate_task_error_message("拉数/入库失败: " + "; ".join(all_failures))
        set_task_result(GAM_API_TASK_NAME, message)
        raise RuntimeError(message)

    # 部分账号失败：仍抛错，确保 last_error 显示失败原因，且不计入 success_count
    if all_failures:
        result = "部分失败: " + "; ".join(all_failures)
        if phase_summaries:
            result += " | 成功账号: " + "; ".join(phase_summaries)
        message = truncate_task_error_message(result)
        set_task_result(GAM_API_TASK_NAME, message)
        raise RuntimeError(message)

    result = "执行成功: " + "; ".join(phase_summaries)
    set_task_result(GAM_API_TASK_NAME, truncate_task_error_message(result))
