"""转发日志 API 适配层。"""
from app.services.cpl.postback_forward_log_service import (
    PostbackForwardLogService,
    postback_forward_log_service,
)

ForwardLogHandler = PostbackForwardLogService
forward_log_handler = postback_forward_log_service

__all__ = ["ForwardLogHandler", "PostbackForwardLogService", "forward_log_handler"]
