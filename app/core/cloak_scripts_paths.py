"""
斗篷桥页 HTML 在磁盘上的路径解析与校验工具。

路径查找顺序（与 short_link /change 读取一致）：
1. 生产：/data/Platform/scripts/{cloak_name}.html
2. 开发：{项目根}/scripts/{cloak_name}.html

主要能力：
- resolve_bridge_html_read_path：读取时找首个存在的文件
- resolve_bridge_html_write_path：上传时覆盖已有文件或写入首个可写目录
- read_bridge_html_template_cached：按 mtime 缓存模板内容，降低高并发读盘压力
- validate_bridge_html_bytes：管理端上传前的 UTF-8 / HTML 结构 / 大小 / XSS 消毒校验
"""
from __future__ import annotations

import logging
import os
import re
import stat
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from app.core.bridge_html_sanitize import sanitize_bridge_html_strict

logger = logging.getLogger(__name__)

# 桥页模板 LRU 缓存：键为规范化绝对路径，值为 (mtime_ns, size, inode, 文本内容)
# 文件 mtime 变化或 invalidate_bridge_template_cache 调用时自动失效
_MAX_BRIDGE_TEMPLATE_CACHE_ENTRIES = 128
_bridge_template_cache: OrderedDict[str, tuple[int, int, int, str]] = OrderedDict()

# 生产环境桥页根目录（与部署脚本约定一致）
SCRIPTS_DIR_SERVER = "/data/Platform/scripts"


def _project_scripts_dir() -> str:
    """本地开发环境桥页目录：项目根下的 scripts/（app/core -> app -> 根）。"""
    return str(Path(__file__).resolve().parent.parent.parent / "scripts")


def iter_bridge_search_bases() -> tuple[str, str]:
    """返回桥页 HTML 查找/写入的候选根目录：(服务器路径, 本地 scripts 路径)。"""
    return SCRIPTS_DIR_SERVER, _project_scripts_dir()


_SAFE_CLOAK_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def bridge_html_filename(cloak_name: str) -> str:
    """斗篷名对应的桥页文件名；在文件系统边界再次校验，不能只信任 API Schema。"""
    if not isinstance(cloak_name, str) or not _SAFE_CLOAK_NAME_RE.fullmatch(cloak_name):
        raise ValueError("斗篷名称无效：仅支持 1～100 位字母、数字、下划线和中划线")
    return f"{cloak_name}.html"


def resolve_bridge_html_read_path(bridge_page_name: str) -> Optional[str]:
    """返回首个存在的桥页文件绝对路径；仅接受安全的单层 .html 文件名。"""
    if not isinstance(bridge_page_name, str) or not bridge_page_name.endswith(".html"):
        raise ValueError("桥页文件名无效")
    cloak_name = bridge_page_name[:-5]
    if bridge_html_filename(cloak_name) != bridge_page_name:
        raise ValueError("桥页文件名无效")
    for base in iter_bridge_search_bases():
        path = os.path.join(base, bridge_page_name)
        try:
            file_stat = os.lstat(path)
        except FileNotFoundError:
            continue
        # 桥页是应用主动对外返回的 HTML；不跟随符号链接，避免读取脚本目录外文件。
        if stat.S_ISLNK(file_stat.st_mode):
            logger.warning("拒绝读取符号链接桥页：%s", path)
            continue
        if stat.S_ISREG(file_stat.st_mode):
            return path
    return None


def bridge_html_exists(cloak_name: str) -> bool:
    """任一候选路径存在同名文件即视为已部署桥页；历史脏数据按不可用处理。"""
    try:
        filename = bridge_html_filename(cloak_name)
    except ValueError:
        return False
    return resolve_bridge_html_read_path(filename) is not None


def atomic_write_bridge_html(target_path: str, content: str) -> None:
    """
    以同目录临时文件 + os.replace 原子替换桥页，避免并发请求读到截断/半写入 HTML。

    保留已有文件权限；新文件使用 0644。临时文件与目标文件处于同一文件系统，
    确保 os.replace 不跨设备。写入前先 flush + fsync。
    """
    target = os.path.abspath(target_path)
    parent = os.path.dirname(target)
    try:
        target_mode = stat.S_IMODE(os.stat(target).st_mode)
    except FileNotFoundError:
        target_mode = 0o644

    fd, temporary_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(target)}.",
        suffix=".tmp",
        dir=parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, target_mode)
        # 原子替换：读取方只会看到完整旧文件或完整新文件。
        os.replace(temporary_path, target)
        # 尽力持久化目录项；部分平台/文件系统不支持目录 fsync。
        try:
            directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def read_bridge_html_template_cached(absolute_path: str) -> str:
    """
    读取桥页 HTML 模板（带 LRU 内存缓存，按文件 mtime 自动失效）。

    /change 高并发场景下同一 {cloak_name}.html 会被频繁读取；缓存命中时直接返回内存内容，
    文件被管理端上传覆盖后 mtime 变化，下次读取自动刷新。

    Args:
        absolute_path: 桥页文件的绝对路径（通常来自 resolve_bridge_html_read_path）

    Returns:
        HTML 文件全文（UTF-8 字符串）

    Raises:
        OSError: 文件不存在或无法读取时向上抛出
    """
    norm = os.path.normpath(os.path.abspath(absolute_path))
    try:
        st = os.stat(norm)
        # 使用纳秒时间、文件大小和 inode，避免同一秒内原子替换时 mtime 精度碰撞。
        signature = (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        raise

    cached = _bridge_template_cache.get(norm)
    if cached is not None and cached[:3] == signature:
        _bridge_template_cache.move_to_end(norm)
        return cached[3]

    with open(norm, "r", encoding="utf-8") as f:
        content = f.read()

    _bridge_template_cache[norm] = (*signature, content)
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
    """生成桥页文件不可写时的运维提示文案（含 chown/chmod 命令）。"""
    return (
        f"路径：{path}。"
        "若文件属主为 root，请在服务器执行（将运行用户换成实际进程用户，如 www-data）："
        f" sudo chown www-data:www-data {path} && sudo chmod u+w {path}；"
        "或直接删除该文件后在本页重新上传。"
    )


def resolve_bridge_html_write_path(cloak_name: str) -> str:
    """
    决定管理端上传桥页 HTML 时应写入的完整文件路径。

    写入策略（按优先级）：
    1. 若任一候选目录已存在 {cloak_name}.html 且可写 → 覆盖该文件
    2. 若文件存在但不可写、目录可写 → 尝试删除后重写
    3. 若文件不存在 → 写入第一个存在且可写的候选目录
    4. 若服务器目录不可用 → 仅在本地 scripts 下 mkdir 后写入（开发环境）

    Args:
        cloak_name: 斗篷名称，对应文件名 {cloak_name}.html

    Returns:
        可写入的绝对路径字符串

    Raises:
        PermissionError: 文件存在但进程无写权限且无法删除
        FileNotFoundError: 所有候选目录均不可写
    """
    name = bridge_html_filename(cloak_name)
    for base in iter_bridge_search_bases():
        candidate = os.path.join(base, name)
        if os.path.lexists(candidate):
            candidate_stat = os.lstat(candidate)
            if stat.S_ISLNK(candidate_stat.st_mode) or not stat.S_ISREG(candidate_stat.st_mode):
                raise ValueError("桥页目标必须是普通文件，拒绝符号链接或特殊文件")
            if os.access(candidate, os.W_OK):
                return candidate
            # 原子替换只要求父目录可写，不要求旧文件本身可写。
            # 不要提前删除旧文件：若后续上传失败，应保留当前可用桥页。
            if os.access(base, os.W_OK):
                return candidate
            raise PermissionError(
                "桥页文件及其目录均不可写，无法原子替换上传。" + _permission_help_extra(candidate)
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


# 管理端上传桥页 HTML 的最大字节数（2MB），与 cloak_configs API 校验一致
MAX_BRIDGE_HTML_BYTES = 2 * 1024 * 1024


def validate_bridge_html_bytes(raw: bytes) -> str:
    """
    校验管理端上传的桥页 HTML 字节流，返回可写入磁盘的 UTF-8 文本。

    校验项：
    1. 大小不超过 MAX_BRIDGE_HTML_BYTES
    2. 必须为合法 UTF-8 编码（拒绝 GBK 等）
    3. 去掉 BOM 后内容长度 ≥ 20 字符（防止空文件）
    4. 前 4000 字符内须含 <!doctype html> 或 <html（基本 HTML 结构）
    5. XSS 消毒：拒绝 iframe、外链 script、事件属性、javascript: 等危险内容

    Args:
        raw: 上传文件的原始字节

    Returns:
        解码后的 HTML 字符串（保留原始换行，写入时用 utf-8 newline=""）

    Raises:
        ValueError: 任一项校验不通过
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

    return sanitize_bridge_html_strict(text)
