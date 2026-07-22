"""
日志 Handler 工具。

提供多进程 Gunicorn 环境下安全的 RotatingFileHandler，避免并发轮转时
备份文件已被其他 worker 删除导致的 FileNotFoundError；
并提供运行时 ERROR 日志的 Telegram 通知 Handler。
"""
import logging
from logging.handlers import RotatingFileHandler

from app.core.telegram.runtime_error_notify import notify_from_log_record


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    多进程安全的轮转 Handler。
    多个 worker 同时轮转时，备份文件可能已被其他进程删除，忽略 FileNotFoundError。
    """

    def doRollover(self) -> None:
        """
        执行日志轮转；多 worker 并发时备份文件可能已被其他进程删除，忽略 FileNotFoundError。

        继承自 RotatingFileHandler，仅在轮转阶段增加容错，不改变轮转策略。
        """
        try:
            super().doRollover()
        except FileNotFoundError:
            pass


class TelegramRuntimeErrorHandler(logging.Handler):
    """
    将带异常信息的 ERROR/CRITICAL 日志推送至管理员 Telegram。

    仅处理 exc_info 非空的记录，避免普通 error 文案刷屏；发送在独立线程中执行。
    """

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return
        if not record.exc_info:
            return
        try:
            notify_from_log_record(record)
        except Exception:
            # 通知失败不得影响正常日志
            pass
