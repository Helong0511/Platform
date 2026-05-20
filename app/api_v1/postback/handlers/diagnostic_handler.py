"""诊断 API 适配层。"""
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
