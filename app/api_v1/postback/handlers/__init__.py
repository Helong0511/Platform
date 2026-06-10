"""Postback 服务实例统一导出（供 routes 与 postback 包引用）。

直接从 app.services.cpl 导入各 Service 单例，不再经独立 adapter 文件中转。
"""
from app.services.cpl.postback_conversion_service import conversion_handler
from app.services.cpl.postback_stats_service import postback_stats_service as stats_handler
from app.services.cpl.postback_forward_log_service import postback_forward_log_service as forward_log_handler
from app.services.cpl.postback_diagnostic_service import postback_diagnostic_service as diagnostic_handler
from app.services.cpl.postback_pending_service import postback_pending_service as pending_handler
from app.services.cpl.postback_duplicate_service import postback_duplicate_service as duplicate_handler
from app.services.cpl.postback_receive_service import postback_receive_service as receive_handler

__all__ = [
    "conversion_handler",
    "stats_handler",
    "forward_log_handler",
    "diagnostic_handler",
    "pending_handler",
    "duplicate_handler",
    "receive_handler",
]
