"""Postback 接收 API 适配层。

导出 PostbackReceiveService 实例，供上游广告主回调转化时
解析参数、校验 IP 白名单、归因点击并触发下游转发。
核心接收流水线在 app.services.cpl.postback_receive_service 中实现。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
from app.services.cpl.postback_receive_service import (
    PostbackReceiveService,
    ReceiveHandler,
    postback_receive_service,
    receive_handler,
)

__all__ = [
    "ReceiveHandler",
    "PostbackReceiveService",
    "receive_handler",
    "postback_receive_service",
]
