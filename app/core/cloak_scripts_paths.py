"""
斗篷桥页 HTML 在磁盘上的路径解析（与 short_link.router 读取顺序保持一致）。

优先使用服务器目录 /data/Platform/scripts，其次为项目根目录下的 scripts/。
"""
from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path
from typing import Optional

# 桥页模板内存缓存（路径规范化 -> (mtime, 内容)），mtime 变化自动失效；减轻 /change 每次读盘
_MAX_BRIDGE_TEMPLATE_CACHE_ENTRIES = 128
_bridge_template_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()

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


def read_bridge_html_template_cached(absolute_path: str) -> str:
    """
    读取桥页 HTML 模板（带内存缓存，按 mtime 失效）。
    用于 /change：同一文件高并发下避免重复磁盘 IO。
    """
    norm = os.path.normpath(os.path.abspath(absolute_path))
    try:
        st = os.stat(norm)
        mtime = st.st_mtime
    except OSError:
        raise

    cached = _bridge_template_cache.get(norm)
    if cached is not None and cached[0] == mtime:
        _bridge_template_cache.move_to_end(norm)
        return cached[1]

    with open(norm, "r", encoding="utf-8") as f:
        content = f.read()

    _bridge_template_cache[norm] = (mtime, content)
    _bridge_template_cache.move_to_end(norm)
    while len(_bridge_template_cache) > _MAX_BRIDGE_TEMPLATE_CACHE_ENTRIES:
        _bridge_template_cache.popitem(last=False)

    return content


def invalidate_bridge_template_cache(path: Optional[str] = None) -> None:
    """上传或替换桥页后可调用；不传 path 则清空全部模板缓存。"""
    global _bridge_template_cache
    if path is None:
        _bridge_template_cache = OrderedDict()
        return
    norm = os.path.normpath(os.path.abspath(path))
    _bridge_template_cache.pop(norm, None)


def _permission_help_extra(path: str) -> str:
    return (
        f"路径：{path}。"
        "若文件属主为 root，请在服务器执行（将运行用户换成实际进程用户，如 www-data）："
        f" sudo chown www-data:www-data {path} && sudo chmod u+w {path}；"
        "或直接删除该文件后在本页重新上传。"
    )


def resolve_bridge_html_write_path(cloak_name: str) -> str:
    """
    决定写入的完整路径：若已有文件则覆盖该路径；否则写入第一个存在且可写的目录。
    """
    name = bridge_html_filename(cloak_name)
    for base in iter_bridge_search_bases():
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            if os.access(candidate, os.W_OK):
                return candidate
            # 文件存在但不可写：目录可写时尝试删除后重写（等价覆盖）
            if os.access(base, os.W_OK):
                try:
                    os.remove(candidate)
                    return candidate
                except OSError:
                    pass
            raise PermissionError(
                "桥页文件不可写，无法覆盖上传。" + _permission_help_extra(candidate)
            )

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
