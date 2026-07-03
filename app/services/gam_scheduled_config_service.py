"""
GAM 定时任务配置服务（管理端 API 层）。

配置与白名单统一保存在 config/gam_scheduler.json。
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.scheduler_module import gam_scheduler_config as gam_cfg


def _map_config_error(exc: Exception) -> None:
    from app.scheduler_module.gam_fetch import normalize_gam_api_exception

    exc = normalize_gam_api_exception(exc)
    if isinstance(exc, FileNotFoundError):
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=str(exc),
        )
    if isinstance(exc, (ValueError, PermissionError)):
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=str(exc),
        )
    raise_api_exception(
        ErrorCode.OPERATION_FAILED,
        detail=str(exc),
    )


async def get_gam_scheduler_config(_db=None) -> dict[str, Any]:
    """读取 GAM 多账号完整配置。"""
    try:
        return await asyncio.to_thread(gam_cfg.get_gam_scheduler_config_payload)
    except Exception as exc:
        _map_config_error(exc)


async def save_gam_scheduler_config(
    _db,
    *,
    accounts: list[dict[str, Any]],
    description: str | None = None,
) -> dict[str, Any]:
    """全量保存 GAM 多账号配置（含白名单与每账号报表类型）。"""
    try:
        return await asyncio.to_thread(
            gam_cfg.save_gam_scheduler_accounts,
            accounts,
            description=description,
        )
    except Exception as exc:
        _map_config_error(exc)


async def refresh_gam_report_types(
    _db,
    *,
    account_key: str | None = None,
    credentials_json: str | None = None,
    application_name: str | None = None,
) -> dict[str, Any]:
    """通过 GAM API 探测指定账号并返回其可用报表类型目录。"""
    from app.scheduler_module.gam_fetch import refresh_gam_report_types_for_account

    try:
        if str(credentials_json or "").strip():
            account = await asyncio.to_thread(
                gam_cfg.build_gam_probe_account,
                key=str(account_key or "probe").strip() or "probe",
                credentials_json=str(credentials_json).strip(),
                application_name=str(application_name or "").strip(),
            )
        else:
            account = await asyncio.to_thread(
                gam_cfg.pick_gam_account_for_report_probe,
                account_key=account_key,
            )
        return await asyncio.to_thread(
            refresh_gam_report_types_for_account,
            account,
        )
    except Exception as exc:
        _map_config_error(exc)


async def upload_gam_credentials_file(
    _db,
    *,
    raw: bytes,
    original_filename: str,
    network_code: str | None = None,
) -> dict[str, Any]:
    """上传并保存 GAM 服务账号密钥 JSON。"""
    from app.scheduler_module.gam_credentials_storage import save_gam_credentials_upload

    try:
        return await asyncio.to_thread(
            save_gam_credentials_upload,
            raw,
            original_filename=original_filename,
            network_code=network_code,
        )
    except Exception as exc:
        _map_config_error(exc)
