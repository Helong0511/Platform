"""Postback 诊断 API 适配层。

导出 PostbackDiagnosticService 实例，供管理端排查转化归因、
点击匹配、转发失败等问题的诊断接口使用。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
from app.services.cpl.postback_diagnostic_service import (
    DiagnosticHandler,
    PostbackDiagnosticService,
    diagnostic_handler,
    postback_diagnostic_service,
)

__all__ = [
    "DiagnosticHandler",
    "PostbackDiagnosticService",
    "diagnostic_handler",
    "postback_diagnostic_service",
]
