"""
斗篷桥页 HTML 在磁盘上的路径解析（与 short_link.router 读取顺序保持一致）。

优先使用服务器目录 /data/Platform/scripts，其次为项目根目录下的 scripts/。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

SCRIPTS_DIR_SERVER = "/data/Platform/scripts"


def _project_scripts_dir() -> str:
    # app/core -> app -> 项目根
    return str(Path(__file__).resolve().parent.parent.parent / "scripts")


def iter_bridge_search_bases() -> tuple[str, str]:
    """返回 (服务器路径, 本地项目 scripts 路径)。"""
    return SCRIPTS_DIR_SERVER, _project_scripts_dir()


def bridge_html_filename(cloak_name: str) -> str:
    return f"{cloak_name}.html"


def resolve_bridge_html_read_path(bridge_page_name: str) -> Optional[str]:
    """返回首个存在的桥页文件绝对路径（与 /change 读取顺序一致：服务器目录优先）。"""
    for base in iter_bridge_search_bases():
        path = os.path.join(base, bridge_page_name)
        if os.path.isfile(path):
            return path
    return None


def bridge_html_exists(cloak_name: str) -> bool:
    """任一候选路径存在同名文件即视为已部署桥页。"""
    return resolve_bridge_html_read_path(bridge_html_filename(cloak_name)) is not None


def resolve_bridge_html_write_path(cloak_name: str) -> str:
    """
    决定写入的完整路径：若已有文件则覆盖该路径；否则写入第一个存在且可写的目录。
    """
    name = bridge_html_filename(cloak_name)
    for base in iter_bridge_search_bases():
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            if not os.access(candidate, os.W_OK):
                raise PermissionError(f"桥页文件不可写：{candidate}")
            return candidate

    server, local = iter_bridge_search_bases()
    for base in (server, local):
        if os.path.isdir(base) and os.access(base, os.W_OK):
            return os.path.join(base, name)

    # 仅在本地项目 scripts 下尝试创建目录（避免在服务器上主动创建 /data/...）
    os.makedirs(local, mode=0o755, exist_ok=True)
    if os.path.isdir(local) and os.access(local, os.W_OK):
        return os.path.join(local, name)

    raise FileNotFoundError(
        "无法写入桥页目录：请确认 /data/Platform/scripts 或项目 scripts 目录存在且进程可写"
    )


MAX_BRIDGE_HTML_BYTES = 2 * 1024 * 1024


def validate_bridge_html_bytes(raw: bytes) -> str:
    """
    校验上传内容为 UTF-8 HTML，返回解码后的文本（用于写入磁盘）。
    """
    if len(raw) > MAX_BRIDGE_HTML_BYTES:
        raise ValueError(f"HTML 文件过大，限制 {MAX_BRIDGE_HTML_BYTES // (1024 * 1024)}MB")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("HTML 须为 UTF-8 编码") from exc

    stripped = text.lstrip("\ufeff").lstrip()
    if len(stripped) < 20:
        raise ValueError("HTML 内容过短")

    head = stripped[:4000].lower()
    if "<html" not in head and "<!doctype html" not in head:
        raise ValueError("文件内容需为 HTML（需包含 <!DOCTYPE html> 或 <html>）")

    return text
