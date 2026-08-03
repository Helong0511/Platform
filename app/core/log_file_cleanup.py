"""
文件日志超期清理与归档。

扫描 ``logs/`` 白名单文件：轮转备份按 mtime 超期归档（gzip）或删除；
归档包超期删除；可选将过大的 gunicorn 活跃日志做溢出轮转；
目录用量超过软/硬限制时告警并紧急清理最旧非 error 备份。

由定时任务 ``cleanup_file_logs`` 调用；核心逻辑为同步函数，便于单测。
"""
from __future__ import annotations

import gzip
import logging
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.core.config import settings
from app.core.constants import LOG_DIR_MODE

logger = logging.getLogger(__name__)

# 磁盘告警防抖（进程内）
_disk_alert_ts: dict[str, float] = {}
_disk_alert_lock = threading.Lock()

# 轮转备份：name.log.1 / name.log.2 …
_BACKUP_SUFFIX_RE = re.compile(r"^(?P<stem>.+\.log)\.(?P<num>\d+)$")
# gunicorn 溢出轮转产生：gunicorn_access.log.20260803_031500
_OVERFLOW_SUFFIX_RE = re.compile(
    r"^(?P<stem>.+\.log)\.(?P<ts>\d{8}_\d{6})$"
)

# 分类：用于保留天数与是否默认归档
_CATEGORY_RULES: tuple[dict[str, Any], ...] = (
    {
        "category": "error",
        "stems": ("error.log",),
        "retention_attr": "LOG_RETENTION_ERROR_DAYS",
        "default_days": 90,
        "prefer_archive": True,
    },
    {
        "category": "warning",
        "stems": ("warning.log",),
        "retention_attr": "LOG_RETENTION_WARNING_DAYS",
        "default_days": 30,
        "prefer_archive": True,
    },
    {
        "category": "app",
        "stems": (
            "app.log",
            "scheduler.log",
            "telegram.log",
            "postback.log",
            "tracking.log",
            "auth.log",
        ),
        "retention_attr": "LOG_RETENTION_APP_DAYS",
        "default_days": 14,
        "prefer_archive": True,
    },
    {
        "category": "access",
        "stems": ("access.log",),
        "retention_attr": "LOG_RETENTION_ACCESS_DAYS",
        "default_days": 7,
        "prefer_archive": False,
    },
    {
        "category": "info",
        "stems": ("info.log", "debug.log"),
        "retention_attr": "LOG_RETENTION_INFO_DAYS",
        "default_days": 3,
        "prefer_archive": False,
    },
    {
        "category": "gunicorn",
        "stems_prefix": ("gunicorn_",),
        "retention_attr": "LOG_RETENTION_GUNICORN_DAYS",
        "default_days": 14,
        "prefer_archive": True,
    },
)

# 永不删除的活跃主文件（无数字后缀）
_ACTIVE_BASENAMES = frozenset(
    {
        "app.log",
        "error.log",
        "warning.log",
        "info.log",
        "access.log",
        "scheduler.log",
        "telegram.log",
        "postback.log",
        "tracking.log",
        "auth.log",
        "debug.log",
        "gunicorn_access.log",
        "gunicorn_error.log",
        "gunicorn_scheduler_access.log",
        "gunicorn_scheduler_error.log",
        "gunicorn.pid",
        "gunicorn_scheduler.pid",
    }
)


@dataclass
class CleanupStats:
    """单次清理结果统计。"""

    deleted_count: int = 0
    archived_count: int = 0
    bytes_freed: int = 0
    overflow_rotated: int = 0
    errors: list[str] = field(default_factory=list)
    soft_limit_hit: bool = False
    hard_limit_hit: bool = False
    emergency_deleted: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "deleted_count": self.deleted_count,
            "archived_count": self.archived_count,
            "bytes_freed": self.bytes_freed,
            "overflow_rotated": self.overflow_rotated,
            "errors": list(self.errors),
            "soft_limit_hit": self.soft_limit_hit,
            "hard_limit_hit": self.hard_limit_hit,
            "emergency_deleted": self.emergency_deleted,
            "message": self.summary_message(),
        }

    def summary_message(self) -> str:
        return (
            f"归档 {self.archived_count}，删除 {self.deleted_count}，"
            f"溢出轮转 {self.overflow_rotated}，释放 {self.bytes_freed} 字节"
            + (f"，紧急清理 {self.emergency_deleted}" if self.emergency_deleted else "")
            + (f"，错误 {len(self.errors)}" if self.errors else "")
        )


def resolve_log_directory() -> Path:
    """解析日志目录（与 logging_setup / gunicorn 一致）。"""
    project_root = Path(__file__).resolve().parents[2]
    log_file = getattr(settings, "LOG_FILE", "logs/app.log") or "logs/app.log"
    if os.path.isabs(log_file):
        return Path(os.path.dirname(log_file))
    return project_root / (os.path.dirname(log_file) or "logs")


def resolve_archive_directory(log_dir: Path | None = None) -> Path:
    """解析归档目录。"""
    log_dir = log_dir or resolve_log_directory()
    archive_rel = getattr(settings, "LOG_ARCHIVE_DIR", "logs/archive") or "logs/archive"
    if os.path.isabs(archive_rel):
        return Path(archive_rel)
    # 相对路径：相对项目根
    project_root = Path(__file__).resolve().parents[2]
    return project_root / archive_rel


def _env_int(attr: str, default: int) -> int:
    try:
        return int(getattr(settings, attr, default))
    except (TypeError, ValueError):
        return default


def _category_for_stem(stem: str) -> dict[str, Any] | None:
    for rule in _CATEGORY_RULES:
        stems = rule.get("stems") or ()
        if stem in stems:
            return rule
        prefixes = rule.get("stems_prefix") or ()
        if any(stem.startswith(p) for p in prefixes):
            return rule
    return None


def classify_log_basename(basename: str) -> tuple[str, str, int, bool] | None:
    """
    分类可清理备份文件。

    Returns:
        (category, active_stem, retention_days, prefer_archive) 或 None（不可清理）
    """
    if basename in _ACTIVE_BASENAMES:
        return None
    m = _BACKUP_SUFFIX_RE.match(basename) or _OVERFLOW_SUFFIX_RE.match(basename)
    if not m:
        return None
    stem = m.group("stem")
    rule = _category_for_stem(stem)
    if rule is None:
        return None
    days = _env_int(rule["retention_attr"], int(rule["default_days"]))
    return (
        str(rule["category"]),
        stem,
        days,
        bool(rule["prefer_archive"]),
    )


def _file_age_days(path: Path, now_ts: float | None = None) -> float:
    now_ts = now_ts if now_ts is not None else time.time()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return 0.0
    return max(0.0, (now_ts - mtime) / 86400.0)


def _dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                if fp.is_symlink():
                    continue
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def _safe_unlink(path: Path, stats: CleanupStats) -> None:
    try:
        size = path.stat().st_size
        path.unlink()
        stats.deleted_count += 1
        stats.bytes_freed += size
    except OSError as exc:
        stats.errors.append(f"删除失败 {path}: {exc}")


def _archive_file(path: Path, category: str, archive_root: Path, stats: CleanupStats) -> None:
    try:
        dest_dir = archive_root / category
        dest_dir.mkdir(parents=True, exist_ok=True, mode=LOG_DIR_MODE)
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        date_tag = mtime.strftime("%Y-%m-%d")
        base = path.name
        dest = dest_dir / f"{base}.{date_tag}.gz"
        # 避免重名覆盖
        seq = 1
        while dest.exists():
            dest = dest_dir / f"{base}.{date_tag}.{seq}.gz"
            seq += 1
        size = path.stat().st_size
        with path.open("rb") as src, gzip.open(dest, "wb") as gz:
            shutil.copyfileobj(src, gz, length=1024 * 1024)
        path.unlink()
        stats.archived_count += 1
        stats.bytes_freed += max(0, size - dest.stat().st_size)
    except OSError as exc:
        stats.errors.append(f"归档失败 {path}: {exc}")


def _iter_log_dir_files(log_dir: Path) -> Iterable[Path]:
    if not log_dir.is_dir():
        return []
    for entry in log_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.is_symlink():
            continue
        yield entry


def _notify_disk_limit_telegram(level: str, usage_mb: int, limit_mb: int, log_dir: Path) -> None:
    """磁盘软/硬限制 Telegram 告警（失败不影响清理主流程）。"""
    if not bool(getattr(settings, "LOG_DISK_TELEGRAM_NOTIFY", True)):
        return
    if not bool(getattr(settings, "TELEGRAM_ENABLE", True)):
        return
    admin = getattr(settings, "TELEGRAM_ADMIN", None)
    if not admin or not str(admin).strip():
        return

    debounce = int(getattr(settings, "LOG_DISK_TELEGRAM_DEBOUNCE_SECONDS", 3600) or 3600)
    key = f"log_disk_{level}"
    now = time.time()
    with _disk_alert_lock:
        last = _disk_alert_ts.get(key, 0.0)
        if now - last < debounce:
            return
        _disk_alert_ts[key] = now

    try:
        from app.core.telegram.message_sender import send_telegram_message
        from app.core.telegram.service_notify import get_service_display_name

        title = "日志磁盘软限制告警" if level == "soft" else "日志磁盘硬限制告警"
        emoji = "⚠️" if level == "soft" else "🚨"
        msg = (
            f"{emoji} {title}\n\n"
            f"服务：{get_service_display_name()}\n"
            f"目录：{log_dir}\n"
            f"用量：{usage_mb} MB / 限制：{limit_mb} MB\n"
            f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if level == "hard":
            msg += "\n已触发紧急清理（优先删除最旧非 error 备份/归档）"
        send_telegram_message(msg)
    except Exception as exc:
        logger.warning("日志磁盘告警 Telegram 发送失败: %s", exc)


def overflow_rotate_gunicorn_if_needed(
    log_dir: Path,
    stats: CleanupStats,
    max_bytes: int | None = None,
) -> None:
    """活跃 gunicorn 日志超过大小阈值时，改名为带时间戳备份（供后续超期清理）。"""
    max_bytes = max_bytes if max_bytes is not None else _env_int("LOG_MAX_BYTES", 10 * 1024 * 1024)
    for path in _iter_log_dir_files(log_dir):
        name = path.name
        if not name.startswith("gunicorn_") or not name.endswith(".log"):
            continue
        if name not in _ACTIVE_BASENAMES:
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            stats.errors.append(f"读取失败 {path}: {exc}")
            continue
        if size <= max_bytes:
            continue
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = path.with_name(f"{name}.{ts}")
        try:
            # 复制后截断活跃文件，避免移动导致 gunicorn 句柄失效（Windows/部分场景）
            shutil.copy2(path, dest)
            with path.open("w", encoding="utf-8"):
                pass
            stats.overflow_rotated += 1
            logger.warning("gunicorn 日志溢出轮转: %s -> %s (size=%s)", name, dest.name, size)
        except OSError as exc:
            stats.errors.append(f"溢出轮转失败 {path}: {exc}")


def cleanup_expired_backups(
    log_dir: Path,
    archive_root: Path,
    stats: CleanupStats,
    *,
    archive_enabled: bool | None = None,
    now_ts: float | None = None,
) -> None:
    """清理 logs/ 根目录下超期轮转备份。"""
    if archive_enabled is None:
        archive_enabled = bool(getattr(settings, "LOG_FILE_ARCHIVE", True))
    now_ts = now_ts if now_ts is not None else time.time()

    for path in list(_iter_log_dir_files(log_dir)):
        info = classify_log_basename(path.name)
        if info is None:
            continue
        category, _stem, retention_days, prefer_archive = info
        age = _file_age_days(path, now_ts)
        if age < retention_days:
            continue
        do_archive = bool(archive_enabled and prefer_archive)
        if do_archive:
            _archive_file(path, category, archive_root, stats)
        else:
            _safe_unlink(path, stats)


def cleanup_expired_archives(
    archive_root: Path,
    stats: CleanupStats,
    *,
    now_ts: float | None = None,
) -> None:
    """清理 archive/ 内超期 gzip。"""
    if not archive_root.is_dir():
        return
    now_ts = now_ts if now_ts is not None else time.time()
    # error 归档默认 180 天；其它类别归档默认 60 天（可用配置覆盖上限）
    error_archive_days = _env_int("LOG_ARCHIVE_RETENTION_DAYS", 180)
    other_archive_days = min(error_archive_days, 60)

    for root, _dirs, files in os.walk(archive_root):
        try:
            rel = Path(root).relative_to(archive_root)
            category = rel.parts[0] if rel.parts else "misc"
        except ValueError:
            category = "misc"
        keep_days = error_archive_days if category == "error" else other_archive_days

        for name in files:
            if not name.endswith(".gz"):
                continue
            path = Path(root) / name
            if path.is_symlink():
                continue
            if _file_age_days(path, now_ts) >= keep_days:
                _safe_unlink(path, stats)


def enforce_disk_limits(
    log_dir: Path,
    archive_root: Path,
    stats: CleanupStats,
) -> None:
    """磁盘软/硬限制守卫。"""
    soft_mb = _env_int("LOG_DISK_SOFT_LIMIT_MB", 2048)
    hard_mb = _env_int("LOG_DISK_HARD_LIMIT_MB", 4096)
    soft_bytes = soft_mb * 1024 * 1024
    hard_bytes = hard_mb * 1024 * 1024

    usage = _combined_logs_usage_bytes(log_dir, archive_root)

    if usage >= soft_bytes:
        stats.soft_limit_hit = True
        usage_mb = usage // (1024 * 1024)
        logger.warning(
            "日志目录用量达到软限制: %s MB / soft=%s MB",
            usage_mb,
            soft_mb,
        )
        _notify_disk_limit_telegram("soft", usage_mb, soft_mb, log_dir)

    if usage < hard_bytes:
        return

    stats.hard_limit_hit = True
    usage_mb = usage // (1024 * 1024)
    logger.error(
        "日志目录用量达到硬限制: %s MB / hard=%s MB，开始紧急清理非 error 旧文件",
        usage_mb,
        hard_mb,
    )
    _notify_disk_limit_telegram("hard", usage_mb, hard_mb, log_dir)

    candidates: list[tuple[float, Path]] = []
    scan_roots = [log_dir]
    try:
        archive_resolved = archive_root.resolve()
        log_resolved = log_dir.resolve()
        # archive 已在 logs/ 下时不必二次 walk，避免候选重复
        if archive_root.is_dir() and not str(archive_resolved).startswith(str(log_resolved)):
            scan_roots.append(archive_root)
    except OSError:
        if archive_root.is_dir():
            scan_roots.append(archive_root)

    for root in scan_roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                path = Path(dirpath) / name
                if path.name in _ACTIVE_BASENAMES:
                    continue
                if path.name.endswith(".rotate.lock") or path.name.endswith(".pid"):
                    continue
                # 紧急清理跳过 error 类别（备份与归档）
                if "error.log" in path.name or (archive_root in path.parents and "error" in path.parts):
                    # 保留近期 error；超过紧急保留天数仍可删
                    emergency_keep = _env_int("LOG_DISK_EMERGENCY_KEEP_ERROR_DAYS", 30)
                    if _file_age_days(path) < emergency_keep:
                        continue
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                candidates.append((mtime, path))

    candidates.sort(key=lambda x: x[0])  # 最旧优先
    for _mtime, path in candidates:
        usage = _combined_logs_usage_bytes(log_dir, archive_root)
        if usage < hard_bytes * 0.85:
            break
        before = stats.deleted_count
        _safe_unlink(path, stats)
        if stats.deleted_count > before:
            stats.emergency_deleted += 1


def cleanup_stale_rotate_locks(
    log_dir: Path,
    stats: CleanupStats,
    *,
    stale_sec: float = 30.0,
    now_ts: float | None = None,
) -> None:
    """清理异常残留的 *.rotate.lock（轮转锁文件）。"""
    now_ts = now_ts if now_ts is not None else time.time()
    for path in list(_iter_log_dir_files(log_dir)):
        if not path.name.endswith(".rotate.lock"):
            continue
        try:
            age = now_ts - path.stat().st_mtime
        except OSError as exc:
            stats.errors.append(f"读取锁文件失败 {path}: {exc}")
            continue
        if age >= stale_sec:
            _safe_unlink(path, stats)


def cleanup_orphan_files(
    log_dir: Path,
    stats: CleanupStats,
    *,
    now_ts: float | None = None,
) -> None:
    """
    清理 logs/ 根目录下「非活跃、非标准轮转备份」的超龄杂文件。

    例如历史遗留临时文件、误放文件；不碰活跃主文件与 *.rotate.lock。
    """
    orphan_days = _env_int("LOG_RETENTION_ORPHAN_DAYS", 7)
    now_ts = now_ts if now_ts is not None else time.time()
    for path in list(_iter_log_dir_files(log_dir)):
        name = path.name
        if name in _ACTIVE_BASENAMES:
            continue
        if name.endswith(".rotate.lock") or name.endswith(".pid"):
            continue
        if classify_log_basename(name) is not None:
            continue
        if _file_age_days(path, now_ts) < orphan_days:
            continue
        _safe_unlink(path, stats)


def _combined_logs_usage_bytes(log_dir: Path, archive_root: Path) -> int:
    """合计日志用量：logs 目录 +（若 archive 在 logs 外）外置归档目录。"""
    usage = _dir_size_bytes(log_dir)
    try:
        if not archive_root.exists():
            return usage
        log_resolved = log_dir.resolve()
        archive_resolved = archive_root.resolve()
        if archive_resolved == log_resolved:
            return usage
        # archive 在 logs 子目录时 walk 已计入
        if str(archive_resolved).startswith(str(log_resolved)):
            return usage
        usage += _dir_size_bytes(archive_root)
    except OSError:
        pass
    return usage


def get_logs_disk_stats(log_dir: Path | None = None) -> dict[str, Any]:
    """供监控接口返回日志目录用量快照（与磁盘守卫同一套合计逻辑）。"""
    log_dir = log_dir or resolve_log_directory()
    archive_root = resolve_archive_directory(log_dir)
    usage = _combined_logs_usage_bytes(log_dir, archive_root)
    soft_mb = _env_int("LOG_DISK_SOFT_LIMIT_MB", 2048)
    hard_mb = _env_int("LOG_DISK_HARD_LIMIT_MB", 4096)
    usage_mb = usage / (1024 * 1024)
    soft_ratio = round(usage_mb / soft_mb, 4) if soft_mb > 0 else None
    hard_ratio = round(usage_mb / hard_mb, 4) if hard_mb > 0 else None
    return {
        "path": str(log_dir),
        "archive_path": str(archive_root),
        "bytes": usage,
        "usage_mb": round(usage_mb, 2),
        "soft_limit_mb": soft_mb,
        "hard_limit_mb": hard_mb,
        "soft_limit_hit": usage_mb >= soft_mb,
        "hard_limit_hit": usage_mb >= hard_mb,
        "usage_ratio_soft": soft_ratio,
        "usage_ratio_hard": hard_ratio,
        # 便于前端进度条：相对软限制的百分比（可 >100）
        "usage_percent_soft": round((usage_mb / soft_mb) * 100, 2) if soft_mb > 0 else 0.0,
    }


def run_file_log_cleanup(
    *,
    log_dir: Path | None = None,
    archive_dir: Path | None = None,
    now_ts: float | None = None,
) -> dict[str, Any]:
    """
    执行完整文件日志清理流程。

    Returns:
        统计字典（含 message）
    """
    if not bool(getattr(settings, "LOG_FILE_CLEANUP_ENABLED", True)):
        return {
            "deleted_count": 0,
            "archived_count": 0,
            "bytes_freed": 0,
            "overflow_rotated": 0,
            "errors": [],
            "soft_limit_hit": False,
            "hard_limit_hit": False,
            "emergency_deleted": 0,
            "message": "文件日志清理已禁用（LOG_FILE_CLEANUP_ENABLED=false）",
            "skipped": True,
        }

    stats = CleanupStats()
    log_dir = log_dir or resolve_log_directory()
    archive_root = archive_dir or resolve_archive_directory(log_dir)

    try:
        log_dir.mkdir(parents=True, exist_ok=True, mode=LOG_DIR_MODE)
        archive_root.mkdir(parents=True, exist_ok=True, mode=LOG_DIR_MODE)
    except OSError as exc:
        stats.errors.append(f"创建目录失败: {exc}")
        result = stats.as_dict()
        result["skipped"] = False
        return result

    overflow_rotate_gunicorn_if_needed(log_dir, stats)
    cleanup_stale_rotate_locks(log_dir, stats, now_ts=now_ts)
    cleanup_orphan_files(log_dir, stats, now_ts=now_ts)
    cleanup_expired_backups(log_dir, archive_root, stats, now_ts=now_ts)
    cleanup_expired_archives(archive_root, stats, now_ts=now_ts)
    enforce_disk_limits(log_dir, archive_root, stats)

    result = stats.as_dict()
    result["skipped"] = False
    result["log_dir"] = str(log_dir)
    result["archive_dir"] = str(archive_root)
    return result
