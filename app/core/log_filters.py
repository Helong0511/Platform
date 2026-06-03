"""日志 Filter：按模块路由到分类日志文件。"""
from __future__ import annotations

import logging


class PostbackLoggerFilter(logging.Filter):
    """仅放行 Postback 相关 logger 的记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
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
        method_u = (method or "").upper()
        if method_u in ("PROPFIND", "TRACE", "CONNECT", "OPTIONS"):
            return method_u != "OPTIONS"
        path_l = (path or "").lower()
        return any(m in path_l for m in cls._PROBE_MARKERS)
