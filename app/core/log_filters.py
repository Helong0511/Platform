"""
日志 Filter 工具。

职责：将不同业务模块的日志记录路由到对应分类文件，并识别扫描/探测类请求以降级 CSRF 等日志级别。

在系统中的位置：由 ``app.core.log_utils`` 配置 Handler 时挂载；``CsrfProbePathFilter``
被 ``app.core.csrf`` 用于区分合法前端与自动化扫描。
"""
from __future__ import annotations

import logging


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
