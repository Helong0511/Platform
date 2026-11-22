"""
Telegram Bot 跨平台进程锁。

锁文件只保存诊断元数据；真正的互斥由操作系统文件锁保证。
文件锁句柄必须在持锁期间保持打开，释放时不删除锁文件，避免 unlink 后
其他进程锁住旧 inode、第三个进程又创建新 inode 的双锁竞态。
"""
import errno
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HAS_FCNTL = False
HAS_MSVCRT = False

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    try:
        import msvcrt
        HAS_MSVCRT = True
    except ImportError:
        logger.warning("无法导入文件锁模块（fcntl/msvcrt），Bot 将 fail closed，不启动无锁轮询")

DEFAULT_LOCK_FILE_NAME = "telegram_bot.lock"
LOCK_EXPIRE_SECONDS = 3600  # 仅供旧锁文件诊断；互斥不再依赖时间戳

_bot_lock_file = None
_bot_lock_acquired = False
_bot_lock_path: Optional[Path] = None


def get_default_lock_path() -> Path:
    """获取默认锁文件路径（项目根目录 logs/）。"""
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / DEFAULT_LOCK_FILE_NAME


def _read_lock_metadata(lock_file_path: Path) -> str:
    with open(lock_file_path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _get_lock_pid(lock_file_path: Path) -> Optional[int]:
    """读取锁文件中的 PID（仅诊断，不作为互斥判据）。"""
    try:
        if not lock_file_path.exists():
            return None
        for line in _read_lock_metadata(lock_file_path).splitlines():
            if line.startswith("PID:"):
                try:
                    pid = int(line.partition(":")[2].strip())
                    return pid if pid > 0 else None
                except ValueError:
                    return None
        return None
    except Exception as exc:
        logger.warning("读取锁文件 PID 时出错；error_type=%s", type(exc).__name__)
        return None


def _is_process_running(pid: int) -> bool:
    """检查本机进程是否存在（仅用于诊断锁文件元数据）。"""
    if pid <= 0:
        return False
    try:
        if os.name == "posix":
            os.kill(pid, 0)
            return True
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, 0, pid)
            if handle == 0:
                return False
            kernel32.CloseHandle(handle)
            return True
        return False
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False


def _is_lock_expired(lock_file_path: Path) -> bool:
    """
    判断锁文件元数据是否陈旧。

    活跃 PID 永远不能仅因文件时间戳超过一小时而判定过期。
    注意：该函数只供诊断/兼容旧测试，acquire_bot_lock 以 OS 锁为唯一判据。
    """
    try:
        if not lock_file_path.exists():
            return False
        pid = _get_lock_pid(lock_file_path)
        if pid and _is_process_running(pid):
            return False

        content = _read_lock_metadata(lock_file_path)
        timestamp = None
        for line in content.splitlines():
            if line.startswith("Timestamp:"):
                try:
                    timestamp = float(line.partition(":")[2].strip())
                except ValueError:
                    timestamp = None
                break
        if timestamp is None:
            file_mtime = lock_file_path.stat().st_mtime
            timestamp = file_mtime
        return (time.time() - timestamp) > LOCK_EXPIRE_SECONDS
    except Exception as exc:
        logger.warning("检查锁文件过期状态时出错；error_type=%s", type(exc).__name__)
        return False


def _close_handle(handle) -> None:
    if handle is not None:
        try:
            handle.close()
        except Exception:
            pass


def _write_lock_metadata(handle, current_pid: int) -> None:
    hostname = os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "unknown")
    payload = (
        f"PID: {current_pid}\n"
        f"Timestamp: {time.time()}\n"
        f"Hostname: {hostname}\n"
    ).encode("utf-8")
    handle.seek(0)
    handle.truncate()
    handle.write(payload)
    handle.flush()
    os.fsync(handle.fileno())


def acquire_bot_lock(lock_file_path: Optional[Path] = None, max_retries: int = 3) -> bool:
    """
    使用 fcntl.flock（Linux/macOS）或 msvcrt.locking（Windows）获取互斥锁。

    锁文件保留为稳定 inode，不在释放时删除。无操作系统锁支持时 fail closed。
    """
    global _bot_lock_file, _bot_lock_acquired, _bot_lock_path

    if _bot_lock_acquired and _bot_lock_file is not None:
        # 同一进程的其他线程也不能重复取得全局 Bot 锁。
        logger.info("当前进程已有线程持有 Telegram Bot 锁")
        return False

    if not HAS_FCNTL and not HAS_MSVCRT:
        logger.error("当前平台没有可用的 OS 文件锁，拒绝启动 Telegram 轮询")
        return False

    path = Path(lock_file_path) if lock_file_path is not None else get_default_lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("创建 Telegram 锁目录失败；error_type=%s", type(exc).__name__)
        return False

    retry_delay = 0.2
    for attempt in range(1, max(1, int(max_retries)) + 1):
        handle = None
        locked = False
        try:
            # a+b 不会在获取锁之前截断其他进程正在使用的 inode。
            handle = open(path, "a+b")
            if HAS_FCNTL:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        logger.info("Telegram Bot 锁已由其他进程持有")
                        _close_handle(handle)
                        return False
                    raise
            else:
                # msvcrt 锁定第一个字节；确保文件至少有一个字节。
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        logger.info("Telegram Bot 锁已由其他进程持有")
                        _close_handle(handle)
                        return False
                    raise
            locked = True
            _write_lock_metadata(handle, os.getpid())
            _bot_lock_file = handle
            _bot_lock_path = path
            _bot_lock_acquired = True
            logger.info("成功获取 Telegram Bot OS 文件锁（backend=%s）", "fcntl" if HAS_FCNTL else "msvcrt")
            return True
        except Exception as exc:
            if locked and handle is not None:
                try:
                    if HAS_FCNTL:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    elif HAS_MSVCRT:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            _close_handle(handle)
            logger.warning(
                "获取 Telegram Bot 文件锁失败（尝试 %s/%s）；error_type=%s",
                attempt,
                max(1, int(max_retries)),
                type(exc).__name__,
            )
            if attempt >= max(1, int(max_retries)):
                return False
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 1.0)
    return False


def release_bot_lock() -> None:
    """释放 OS 锁并关闭句柄；保留锁文件，避免 unlink 竞态。"""
    global _bot_lock_file, _bot_lock_acquired, _bot_lock_path

    handle = _bot_lock_file
    path = _bot_lock_path
    if handle is None or not _bot_lock_acquired:
        logger.info("[PID:%s] 当前进程没有持有 Telegram Bot 锁", os.getpid())
        return

    try:
        if HAS_FCNTL:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        elif HAS_MSVCRT:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        logger.info("已释放 Telegram Bot OS 文件锁")
    except Exception as exc:
        logger.warning("释放 Telegram Bot 文件锁失败；error_type=%s", type(exc).__name__)
    finally:
        _close_handle(handle)
        _bot_lock_file = None
        _bot_lock_acquired = False
        _bot_lock_path = None
        if path is not None:
            logger.debug("Telegram Bot 锁文件保留以维持稳定 inode：%s", path)


def is_lock_held() -> bool:
    """检查当前进程是否持有 OS 文件锁句柄。"""
    return _bot_lock_acquired and _bot_lock_file is not None
