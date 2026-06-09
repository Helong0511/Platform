"""Postback 转发日志 API 适配层。

导出 PostbackForwardLogService 实例，供管理端查看平台向下游
渠道转发 Postback 的请求/响应明细与失败原因。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
from app.services.cpl.postback_forward_log_service import (
    PostbackForwardLogService,
    postback_forward_log_service,
)

ForwardLogHandler = PostbackForwardLogService
forward_log_handler = postback_forward_log_service

__all__ = ["ForwardLogHandler", "PostbackForwardLogService", "forward_log_handler"]
