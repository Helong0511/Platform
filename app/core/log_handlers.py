"""
日志 Handler 工具。

提供多进程 Gunicorn 环境下更稳健的 RotatingFileHandler：轮转时使用跨进程文件锁，
并容忍备份文件已被其他 worker 删除等竞态；
另提供运行时 ERROR 日志的 Telegram 通知 Handler。
"""
from __future__ import annotations

import logging
import os
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler

from app.core.telegram.runtime_error_notify import notify_from_log_record


def _write_logging_error_to_real_stderr(record: logging.LogRecord | None = None) -> None:
    """将 Handler 内部异常写到真实 stderr，避免进入已被劫持的 sys.stderr 再记日志。"""
    try:
        stream = getattr(sys, "__stderr__", None) or sys.stderr
        stream.write("--- Logging error ---\n")
        ei = sys.exc_info()
        try:
            if ei[0] is not None:
                traceback.print_exception(ei[0], ei[1], ei[2], None, stream)
        finally:
            del ei
        if record is not None:
            try:
                stream.write(f"Logged from file {record.pathname}, line {record.lineno}\n")
            except Exception:
                pass
        stream.flush()
    except Exception:
        pass


class SafeStderrHandleErrorMixin:
    """覆盖默认 handleError，禁止写回被 LoggingStream 劫持的 sys.stderr。"""

    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802
        _write_logging_error_to_real_stderr(record)


class _ExclusiveFileLock:
    """
    跨进程排他锁（O_EXCL 锁文件），不引入第三方依赖。

    用于日志轮转临界区；获取失败时仍继续轮转（降级为无锁 + 重试容错）。
    """

    def __init__(self, lock_path: str, timeout_sec: float = 2.0, stale_sec: float = 30.0) -> None:
        self.lock_path = lock_path
        self.timeout_sec = timeout_sec
        self.stale_sec = stale_sec
        self._fd: int | None = None

    def acquire(self) -> bool:
        deadline = time.time() + self.timeout_sec
        while time.time() < deadline:
            try:
                self._fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                try:
                    os.write(self._fd, str(os.getpid()).encode("ascii", errors="ignore"))
                except OSError:
                    pass
                return True
            except FileExistsError:
                try:
                    mtime = os.path.getmtime(self.lock_path)
                    if time.time() - mtime > self.stale_sec:
                        os.unlink(self.lock_path)
                        continue
                except OSError:
                    pass
                time.sleep(0.05)
            except OSError:
                return False
        return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass


class SafeRotatingFileHandler(SafeStderrHandleErrorMixin, RotatingFileHandler):
    """
    多进程较安全的轮转 Handler。

    轮转前尝试获取同名 ``.rotate.lock``；持锁后再检查文件大小，避免重复轮转。
    对 FileNotFoundError / PermissionError / OSError 做有限重试。
    """

    _ROLLOVER_RETRIES = 3
    _ROLLOVER_RETRY_SLEEP_SEC = 0.05

    def _still_needs_rollover(self) -> bool:
        """持锁后复查：若其他 worker 已轮转，则当前文件可能已小于阈值。"""
        if self.maxBytes <= 0:
            return True
        try:
            if self.stream is None:
                return True
            self.stream.seek(0, os.SEEK_END)
            return self.stream.tell() >= self.maxBytes
        except OSError:
            return True

    def doRollover(self) -> None:
        """执行日志轮转；优先加跨进程锁，并容忍多 worker 竞态异常。"""
        lock_path = f"{self.baseFilename}.rotate.lock"
        file_lock = _ExclusiveFileLock(lock_path)
        locked = file_lock.acquire()
        try:
            if not self._still_needs_rollover():
                return

            last_exc: Exception | None = None
            for attempt in range(self._ROLLOVER_RETRIES):
                try:
                    super().doRollover()
                    return
                except FileNotFoundError as exc:
                    last_exc = exc
                    break
                except PermissionError as exc:
                    last_exc = exc
                    if attempt + 1 < self._ROLLOVER_RETRIES:
                        time.sleep(self._ROLLOVER_RETRY_SLEEP_SEC)
                        continue
                    break
                except OSError as exc:
                    last_exc = exc
                    if attempt + 1 < self._ROLLOVER_RETRIES:
                        time.sleep(self._ROLLOVER_RETRY_SLEEP_SEC)
                        continue
                    break
            if last_exc is not None and not isinstance(last_exc, FileNotFoundError):
                # 最终仍失败时静默跳过，避免拖垮业务
                pass
        finally:
            if locked:
                file_lock.release()


class TelegramRuntimeErrorHandler(SafeStderrHandleErrorMixin, logging.Handler):
    """
    将带异常信息的 ERROR/CRITICAL 日志推送至管理员 Telegram。

    优先使用 ``exc_info``；异步队列兜底场景也可凭 ``exc_text`` 触发。
    文件落盘（error.log）与本 Handler 解耦：无栈 ERROR 仍应写入错误文件。
    """

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return
        if not record.exc_info and not getattr(record, "exc_text", None):
            return
        try:
            notify_from_log_record(record)
        except Exception:
            # 通知失败不得影响正常日志
            pass
