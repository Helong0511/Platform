"""
日志 Filter 工具。

职责：将不同业务模块的日志记录路由到对应分类文件，按级别拆分文件，
并对消息中的常见敏感字段做打码；``CsrfProbePathFilter`` 识别扫描/探测类请求。

在系统中的位置：由 ``app.bootstrap.logging_setup`` 配置 Handler 时挂载；
``CsrfProbePathFilter`` 被 ``app.core.csrf`` 用于区分合法前端与自动化扫描。
"""
from __future__ import annotations

import logging
import re


class LevelRangeFilter(logging.Filter):
    """仅放行级别落在 [min_level, max_level] 闭区间内的记录。"""

    def __init__(self, min_level: int, max_level: int, name: str = "") -> None:
        super().__init__(name)
        self.min_level = int(min_level)
        self.max_level = int(max_level)

    def filter(self, record: logging.LogRecord) -> bool:
        return self.min_level <= record.levelno <= self.max_level


class LoggerNamePrefixFilter(logging.Filter):
    """仅放行 logger 名等于或位于给定前缀命名空间下的记录。"""

    def __init__(self, prefixes: tuple[str, ...] | list[str], name: str = "") -> None:
        super().__init__(name)
        self.prefixes = tuple(prefixes)

    def filter(self, record: logging.LogRecord) -> bool:
        n = record.name or ""
        for prefix in self.prefixes:
            if n == prefix or n.startswith(prefix + "."):
                return True
        return False


class LoggerNameExactFilter(logging.Filter):
    """仅放行精确匹配的 logger 名。"""

    def __init__(self, names: tuple[str, ...] | list[str], name: str = "") -> None:
        super().__init__(name)
        self.names = frozenset(names)

    def filter(self, record: logging.LogRecord) -> bool:
        return (record.name or "") in self.names


class LoggerNameRejectFilter(logging.Filter):
    """拒绝精确匹配的 logger 名（用于队列模式下隔离 access 等）。"""

    def __init__(self, names: tuple[str, ...] | list[str], name: str = "") -> None:
        super().__init__(name)
        self.names = frozenset(names)

    def filter(self, record: logging.LogRecord) -> bool:
        return (record.name or "") not in self.names

class ErrorLogFormatter(logging.Formatter):
    """error.log 专用格式：无异常栈时追加 [no_exc_info]，便于区分纯文案 ERROR。"""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if record.levelno < logging.ERROR:
            return message
        has_exc = bool(record.exc_info) or bool(getattr(record, "exc_text", None))
        if not has_exc and "Traceback (most recent call last)" not in message:
            if "[no_exc_info]" not in message:
                message = f"{message} [no_exc_info]"
        return message


class PostbackLoggerFilter(logging.Filter):
    """仅放行 Postback 相关 logger 的记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """
        仅放行 Postback 相关 logger 的日志记录。

        Args:
            record: 待写入的日志记录

        Returns:
            True 表示写入 postback 专用日志文件，False 表示跳过
        """
        name = record.name
        if name.startswith("app.core.postback"):
            return True
        return name.startswith("app.services.cpl.") and "postback" in name


class SensitiveDataFilter(logging.Filter):
    """对日志消息中的常见敏感键值做轻量打码（不解析结构化 extras）。"""

    _KEY_VALUE = re.compile(
        r"(?i)\b(password|passwd|pwd|token|access_token|refresh_token|"
        r"authorization|secret|api[_-]?key|client_secret)\b(\s*[:=]\s*)([^\s,&;]+)"
    )
    _JSON_VALUE = re.compile(
        r'(?i)("(?:password|passwd|pwd|token|access_token|refresh_token|'
        r'authorization|secret|api[_-]?key|client_secret)"\s*:\s*")([^"]*)(")'
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = self._KEY_VALUE.sub(r"\1\2***", msg)
        redacted = self._JSON_VALUE.sub(r"\1***\3", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


class CsrfProbePathFilter:
    """判断是否为扫描/探测类请求（用于降级日志级别）。"""

    _PROBE_MARKERS = (
        "phpunit",
        "eval-stdin",
        "fortigate",
        "fabric_device",
        ".env",
        "wp-admin",
        "actuator",
        "wlwmanifest",
    )

    @classmethod
    def is_probe(cls, method: str, path: str) -> bool:
        """
        判断请求是否像自动化扫描/漏洞探测（非业务前端）。

        Args:
            method: HTTP 方法
            path: 请求路径

        Returns:
            True 表示探测类请求，日志可降级为 INFO
        """
        method_u = (method or "").upper()
        if method_u in ("PROPFIND", "TRACE", "CONNECT", "OPTIONS"):
            return method_u != "OPTIONS"
        path_l = (path or "").lower()
        return any(m in path_l for m in cls._PROBE_MARKERS)
