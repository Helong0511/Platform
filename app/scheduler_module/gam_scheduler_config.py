"""
GAM 定时任务 JSON 配置读写。

配置文件默认路径：项目根目录 config/gam_scheduler.json
可通过环境变量 GAM_SCHEDULER_CONFIG 覆盖。

每个账号包含：
- key / credentials_json / application_name：拉数账号信息
- report_keys：该账号拉取的报表类型（多选，默认 ad_unit / country / site）
- product_whitelist：产品白名单（空数组=全量拉取）
"""
from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GAM_SCHEDULER_CONFIG_PATH = ROOT / "config" / "gam_scheduler.json"

GAM_CREDENTIALS_NETWORK_PATTERN = re.compile(r"gam-(\d+)\.json$", re.I)

DEFAULT_GAM_REPORT_KEYS: tuple[str, ...] = ("ad_unit", "country", "site")


def get_gam_scheduler_config_path() -> Path:
    """解析 GAM 调度配置文件路径。"""
    raw = (os.getenv("GAM_SCHEDULER_CONFIG") or "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        return path
    return DEFAULT_GAM_SCHEDULER_CONFIG_PATH


def gam_scheduler_config_exists() -> bool:
    """GAM 调度配置文件是否存在。"""
    return get_gam_scheduler_config_path().is_file()


def _load_gam_report_type_keys() -> frozenset[str]:
    from app.scheduler_module.gam_fetch import get_gam_report_types_catalog

    return frozenset(item["key"] for item in get_gam_report_types_catalog())


def normalize_report_keys(keys: list[str] | str | None) -> list[str]:
    """报表类型多选规范化；未配置时使用默认定时任务报表集。"""
    if keys is None:
        return list(DEFAULT_GAM_REPORT_KEYS)

    if isinstance(keys, (int, float)):
        raise ValueError(
            f"report_keys 必须是字符串数组，不能是数字（疑似误填了 network_code）: {keys!r}"
        )
    if isinstance(keys, str):
        text = keys.strip()
        if not text:
            return list(DEFAULT_GAM_REPORT_KEYS)
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"report_keys JSON 解析失败: {exc}") from exc
            if not isinstance(parsed, list):
                raise ValueError("report_keys JSON 必须是字符串数组")
            keys = parsed
        else:
            keys = [part.strip() for part in text.split(",") if part.strip()]
    elif not isinstance(keys, (list, tuple, set, frozenset)):
        raise ValueError(
            f"report_keys 格式无效，期望字符串数组，实际为 {type(keys).__name__}: {keys!r}"
        )

    known = _load_gam_report_type_keys()
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in keys:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        if key not in known:
            raise ValueError(f"未知报表类型: {key}，可选: {sorted(known)}")
        seen.add(key)
        normalized.append(key)
    if not normalized:
        raise ValueError("至少选择一种报表类型")
    return normalized


def get_gam_report_type_options() -> list[dict[str, Any]]:
    """管理端展示的报表类型选项。"""
    from app.scheduler_module.gam_fetch import get_gam_report_types_catalog

    return get_gam_report_types_catalog()


def normalize_product_whitelist(names: list[str] | None) -> list[str]:
    """白名单名称规范化（小写、去 www、去重排序）。"""
    if names is None:
        return []
    if isinstance(names, (int, float)):
        raise ValueError(f"product_whitelist 必须是字符串数组，不能是数字: {names!r}")
    if isinstance(names, str):
        names = [names] if names.strip() else []
    elif not isinstance(names, (list, tuple, set, frozenset)):
        raise ValueError(
            f"product_whitelist 格式无效，期望字符串数组，实际为 {type(names).__name__}: {names!r}"
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = str(raw).strip().lower()
        if name.startswith("www."):
            name = name[4:]
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return sorted(normalized)


def _network_code_from_credentials(credentials_json: str) -> str:
    match = GAM_CREDENTIALS_NETWORK_PATTERN.search(str(credentials_json or ""))
    return match.group(1) if match else ""


def _normalize_account_raw(
    raw: dict[str, Any],
    *,
    default_report_keys: list[str] | None = None,
) -> dict[str, Any]:
    """规范化单个账号配置。"""
    key = str(raw.get("key") or "").strip()
    if not key:
        raise ValueError("GAM 账号缺少 key")

    credentials_json = str(
        raw.get("credentials_json") or raw.get("credentials_path") or ""
    ).strip()
    if not credentials_json:
        raise ValueError(f"GAM 账号 {key} 缺少 credentials_json")

    application_name = str(
        raw.get("application_name") or raw.get("applicationName") or ""
    ).strip()

    product_whitelist = normalize_product_whitelist(raw.get("product_whitelist"))

    if "report_keys" in raw:
        report_keys = normalize_report_keys(raw.get("report_keys"))
    elif default_report_keys is not None:
        report_keys = normalize_report_keys(default_report_keys)
    else:
        report_keys = normalize_report_keys(None)

    return {
        "key": key,
        "credentials_json": credentials_json,
        "application_name": application_name,
        "product_whitelist": product_whitelist,
        "report_keys": report_keys,
    }


def _normalize_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_accounts = payload.get("accounts")
    if not isinstance(raw_accounts, list):
        raise ValueError("gam_scheduler 配置 accounts 必须是数组")

    # 兼容旧版根级 report_keys：迁移到各账号
    legacy_report_keys: list[str] | None = None
    if payload.get("report_keys") is not None:
        legacy_report_keys = normalize_report_keys(payload.get("report_keys"))

    accounts: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for index, item in enumerate(raw_accounts):
        if not isinstance(item, dict):
            raise ValueError(f"accounts[{index}] 必须是对象")
        account = _normalize_account_raw(item, default_report_keys=legacy_report_keys)
        if account["key"] in seen_keys:
            raise ValueError(f"重复的 GAM 账号 key: {account['key']}")
        seen_keys.add(account["key"])
        accounts.append(account)

    return {
        "version": int(payload.get("version") or 1),
        "description": str(payload.get("description") or "").strip(),
        "accounts": accounts,
    }


def load_gam_scheduler_config() -> dict[str, Any]:
    """读取并规范化 GAM JSON 配置。"""
    path = get_gam_scheduler_config_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"GAM 配置文件不存在: {path}，请创建 config/gam_scheduler.json"
        )

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"GAM 配置文件格式无效: {path}")

    config = _normalize_config_payload(payload)
    config["_config_path"] = str(path)
    return config


def save_gam_scheduler_config(config: dict[str, Any]) -> Path:
    """将 GAM 配置写回 JSON 文件。"""
    path = get_gam_scheduler_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = _normalize_config_payload(config)
    output = {
        "version": normalized["version"],
        "description": normalized["description"],
        "accounts": [
            {
                "key": item["key"],
                "credentials_json": item["credentials_json"],
                "application_name": item["application_name"],
                "report_keys": list(item["report_keys"]),
                "product_whitelist": list(item["product_whitelist"]),
            }
            for item in normalized["accounts"]
        ],
    }

    text = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    logger.info("已保存 GAM 配置: %s（%d 个账号）", path, len(output["accounts"]))
    return path


def get_gam_scheduler_accounts() -> list[dict[str, Any]]:
    """返回用于拉数的账号列表（含 product_whitelist）。"""
    config = load_gam_scheduler_config()
    accounts: list[dict[str, Any]] = []
    for item in config["accounts"]:
        account = deepcopy(item)
        account["product_whitelist"] = list(item["product_whitelist"])
        account["report_keys"] = list(item.get("report_keys") or DEFAULT_GAM_REPORT_KEYS)
        accounts.append(account)
    return accounts


def build_gam_account_view(account: dict[str, Any]) -> dict[str, Any]:
    """构建管理端展示用的单账号视图。"""
    effective = list(account.get("product_whitelist") or [])
    credentials_json = account.get("credentials_json") or ""
    credentials_path = Path(credentials_json)
    if not credentials_path.is_absolute():
        credentials_path = ROOT / credentials_json
    return {
        "key": account["key"],
        "network_code": _network_code_from_credentials(credentials_json),
        "application_name": account.get("application_name") or "",
        "credentials_json": credentials_json,
        "credentials_exists": credentials_path.is_file(),
        "product_whitelist": effective,
        "report_keys": list(account.get("report_keys") or DEFAULT_GAM_REPORT_KEYS),
        "fetch_all": len(effective) == 0,
    }


def get_gam_scheduler_config_payload() -> dict[str, Any]:
    """读取完整 GAM 配置（管理端，允许文件不存在或账号为空）。"""
    from app.scheduler_module.task_names import GAM_API_TASK_NAME

    path = get_gam_scheduler_config_path()
    if not path.is_file():
        return {
            "task_name": GAM_API_TASK_NAME,
            "config_path": str(path),
            "config_exists": False,
            "description": "",
            "report_type_options": get_gam_report_type_options(),
            "accounts": [],
        }

    config = load_gam_scheduler_config()
    return {
        "task_name": GAM_API_TASK_NAME,
        "config_path": str(path),
        "config_exists": True,
        "description": config.get("description") or "",
        "report_type_options": get_gam_report_type_options(),
        "accounts": [build_gam_account_view(item) for item in config.get("accounts") or []],
    }


def save_gam_scheduler_accounts(
    accounts: list[dict[str, Any]],
    *,
    description: str | None = None,
) -> dict[str, Any]:
    """全量保存 GAM 多账号配置（含白名单与每账号报表类型），不存在则创建配置文件。"""
    normalized_accounts = [_normalize_account_raw(item) for item in accounts]

    existing_description = ""
    if gam_scheduler_config_exists():
        existing_description = load_gam_scheduler_config().get("description") or ""

    config = {
        "version": 1,
        "description": (
            str(description).strip()
            if description is not None
            else existing_description or "GAM 定时拉数账号与白名单配置（管理端修改会写回此文件）"
        ),
        "accounts": normalized_accounts,
    }
    save_gam_scheduler_config(config)
    return get_gam_scheduler_config_payload()


def build_gam_probe_account(
    *,
    key: str,
    credentials_json: str,
    application_name: str = "",
) -> dict[str, Any]:
    """根据管理端表单字段构建探针用账号（无需已写入配置文件）。"""
    account_key = str(key or "").strip() or "probe"
    return _normalize_account_raw(
        {
            "key": account_key,
            "credentials_json": str(credentials_json).strip(),
            "application_name": str(application_name or "").strip(),
        }
    )


def pick_gam_account_for_report_probe(
    accounts: list[dict[str, Any]] | None = None,
    *,
    account_key: str | None = None,
) -> dict[str, Any]:
    """选择用于探测 GAM API 的账号（优先指定 key，其次首个密钥文件存在的账号）。"""
    source = accounts
    if source is None:
        source = get_gam_scheduler_accounts()

    if not source:
        raise ValueError("未配置 GAM 账号，无法刷新报表类型")

    if account_key:
        key = str(account_key).strip()
        matched = next((item for item in source if item.get("key") == key), None)
        if matched is None:
            raise ValueError(f"未找到 GAM 账号: {key}")
        return matched

    for item in source:
        credentials_json = str(item.get("credentials_json") or "").strip()
        if not credentials_json:
            continue
        credentials_path = Path(credentials_json)
        if not credentials_path.is_absolute():
            credentials_path = ROOT / credentials_json
        if credentials_path.is_file():
            return item

    return source[0]


def resolve_gam_scheduler_accounts() -> list[dict[str, Any]] | None:
    """定时任务拉数入口。"""
    try:
        accounts = get_gam_scheduler_accounts()
    except FileNotFoundError:
        logger.warning("GAM 配置文件不存在，跳过拉数账号加载")
        return None
    return accounts or None
