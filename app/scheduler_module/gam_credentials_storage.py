"""
GAM 服务账号密钥文件上传与存储。

默认目录：项目根目录 secrets/
可通过环境变量 GAM_SECRETS_DIR 覆盖。
"""
from __future__ import annotations

import json
import logging
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GAM_SECRETS_DIR = ROOT / "secrets"
MAX_GAM_CREDENTIALS_BYTES = 256 * 1024

GAM_CREDENTIALS_FILENAME_PATTERN = re.compile(r"^gam-(\d+)\.json$", re.I)
GAM_CREDENTIALS_APP_NAME_KEYS = ("application_name", "applicationName")


def get_gam_secrets_dir() -> Path:
    """解析 GAM 密钥存储目录；生产环境必须显式使用仓库外绝对路径。"""
    raw = (os.getenv("GAM_SECRETS_DIR") or "").strip()
    is_production = os.getenv("PRODUCTION_ENV", "").strip().lower() in {
        "production",
        "prod",
    }

    if is_production:
        if not raw:
            raise RuntimeError("生产环境必须显式配置仓库外的 GAM_SECRETS_DIR")
        path = Path(raw)
        if not path.is_absolute():
            raise ValueError("生产环境 GAM_SECRETS_DIR 必须为绝对路径")
        resolved = path.resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            return resolved
        raise ValueError("生产环境 GAM_SECRETS_DIR 不得位于代码仓库目录内")

    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        return path
    return DEFAULT_GAM_SECRETS_DIR


def parse_network_code_from_filename(filename: str) -> str | None:
    """从上传文件名解析 network_code（gam-{code}.json）。"""
    basename = Path(str(filename or "").strip()).name
    match = GAM_CREDENTIALS_FILENAME_PATTERN.match(basename)
    return match.group(1) if match else None


def _validate_service_account_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("密钥文件必须是 JSON 对象")
    if str(payload.get("type") or "").strip() != "service_account":
        raise ValueError("密钥文件 type 必须为 service_account")
    for key in ("private_key", "client_email", "project_id"):
        if not str(payload.get(key) or "").strip():
            raise ValueError(f"密钥文件缺少必填字段: {key}")
    return payload


def _extract_application_name(payload: dict[str, Any]) -> str:
    for key in GAM_CREDENTIALS_APP_NAME_KEYS:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _relative_path_from_root(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _ensure_writable_file(path: Path) -> None:
    """上传覆盖已有密钥时，清除 Windows 只读等导致无法写入的属性。"""
    if not path.is_file():
        return
    try:
        if os.name != "nt":
            # 覆盖前先收紧旧文件，避免上传期间旧私钥继续保持 group/world-readable。
            path.chmod(0o600)
        else:
            current_mode = path.stat().st_mode
            path.chmod(current_mode | stat.S_IWRITE)
    except OSError as exc:
        raise PermissionError(
            f"密钥文件不可写: {path}，请取消只读属性或关闭占用该文件的程序后重试"
        ) from exc


def _ensure_private_directory(directory: Path) -> None:
    """创建并收紧密钥目录权限；POSIX 下仅允许目录所有者访问。"""
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(directory, 0o700)
    except OSError as exc:
        raise PermissionError(
            f"无法确保 GAM 密钥目录为私有目录: {directory}"
        ) from exc


def _write_credentials_file(target_path: Path, text: str) -> None:
    """以私有权限原子写入密钥文件，避免 umask 过宽暴露服务账号私钥。"""
    _ensure_private_directory(target_path.parent)
    if target_path.is_symlink():
        raise PermissionError("拒绝覆盖符号链接形式的 GAM 密钥文件")

    _ensure_writable_file(target_path)
    # 使用随机临时文件名，避免并发上传同一 network_code 时互相覆盖临时文件。
    tmp_path = target_path.with_name(
        f".{target_path.name}.{uuid.uuid4().hex}.uploading"
    )
    file_mode = 0o600
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    file_descriptor = None
    try:
        # os.open 的 mode 在创建瞬间生效，避免先以 0644 写入再 chmod 的暴露窗口。
        file_descriptor = os.open(tmp_path, flags, file_mode)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            file_descriptor = None
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(tmp_path, file_mode)
        os.replace(tmp_path, target_path)
        if os.name != "nt":
            os.chmod(target_path, file_mode)
    except PermissionError:
        raise
    except OSError as exc:
        raise PermissionError(
            f"无法写入密钥文件 {target_path}：{type(exc).__name__}"
        ) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def save_gam_credentials_upload(
    raw: bytes,
    *,
    original_filename: str,
    network_code: str | None = None,
) -> dict[str, Any]:
    """
    校验并保存 GAM 服务账号 JSON，返回配置页所需字段。

    文件固定保存为 secrets/gam-{network_code}.json（或 GAM_SECRETS_DIR 下同名文件）。
    """
    if len(raw) > MAX_GAM_CREDENTIALS_BYTES:
        raise ValueError(
            f"密钥文件过大，最大允许 {MAX_GAM_CREDENTIALS_BYTES // 1024}KB"
        )

    filename = str(original_filename or "").strip()
    if not filename.lower().endswith(".json"):
        raise ValueError("请上传 .json 格式的密钥文件")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("密钥文件必须是 UTF-8 编码") from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"密钥文件 JSON 格式无效: {exc}") from exc

    payload = _validate_service_account_payload(payload)

    code = str(network_code or "").strip() or (parse_network_code_from_filename(filename) or "")
    if not code.isdigit():
        raise ValueError(
            "无法确定 GAM 网络 ID：请填写网络 ID，或将文件命名为 gam-{网络ID}.json"
        )

    secrets_dir = get_gam_secrets_dir()
    target_path = secrets_dir / f"gam-{code}.json"

    normalized_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    _write_credentials_file(target_path, normalized_text)
    logger.info("已保存 GAM 密钥文件: %s", target_path)

    credentials_json = _relative_path_from_root(target_path)
    application_name = _extract_application_name(payload)
    return {
        "credentials_json": credentials_json,
        "network_code": code,
        "credentials_exists": target_path.is_file(),
        "application_name": application_name,
        "saved_filename": target_path.name,
    }
