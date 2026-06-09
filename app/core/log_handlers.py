"""
日志 Handler 工具。

提供多进程 Gunicorn 环境下安全的 RotatingFileHandler，避免并发轮转时
备份文件已被其他 worker 删除导致的 FileNotFoundError。
"""
import logging
from logging.handlers import RotatingFileHandler


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
