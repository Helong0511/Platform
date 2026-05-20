"""
日志 Handler 工具
"""
import logging
from logging.handlers import RotatingFileHandler


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    多进程安全的轮转 Handler。
    多个 worker 同时轮转时，备份文件可能已被其他进程删除，忽略 FileNotFoundError。
    """

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except FileNotFoundError:
            pass
