"""
GAM API 内存拉数编排。

实现与业务规则见 app.scheduler_module.gam_api_fetch。
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.scheduler_module import gam_api_fetch

logger = logging.getLogger(__name__)

GAM_SCHEDULER_REPORT_KEYS: tuple[str, ...] = gam_api_fetch.GAM_SCHEDULER_REPORT_KEYS


def run_gam_fetch_to_memory(
    start_date: date,
    end_date: date,
    *,
    report_keys: list[str] | None = None,
    accounts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """按日期范围拉取 GAM 多账号报表到内存。"""
    keys = report_keys or list(GAM_SCHEDULER_REPORT_KEYS)
    account_keys = (
        ",".join(str(item.get("key") or "?") for item in accounts)
        if accounts
        else "(默认)"
    )
    logger.info(
        "GAM 内存拉数: %s ~ %s, 报表=%s, 账号=%s",
        start_date.isoformat(),
        end_date.isoformat(),
        ",".join(keys),
        account_keys,
    )
    return gam_api_fetch.run_gam_fetch_to_memory(
        start_date,
        end_date,
        report_keys=keys,
        accounts=accounts,
    )


def get_gam_report_types_catalog() -> list[dict[str, Any]]:
    """返回 GAM 报表类型目录（key / label / dimensions）。"""
    return gam_api_fetch.get_gam_report_types_catalog()


def refresh_gam_report_types_for_account(account: dict[str, Any]) -> dict[str, Any]:
    """用指定账号探测 GAM API 并返回报表类型目录。"""
    return gam_api_fetch.probe_gam_report_types_for_account(account)


def normalize_gam_api_exception(exc: Exception) -> Exception:
    """将 GAM/Google 异常转为带中文说明的 ValueError（若可识别）。"""
    if isinstance(exc, ValueError):
        return exc
    lowered = str(exc).lower()
    if any(token in lowered for token in ("invalid_grant", "access_denied", "permission_denied")):
        return gam_api_fetch.format_gam_auth_error(exc)
    return exc
