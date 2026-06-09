"""待确认转化 API 适配层。

导出 PostbackPendingService 实例，供管理端处理归因不确定、
需人工确认的转化记录（确认/拒绝/批量操作）。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
from app.services.cpl.postback_pending_service import (
    PendingHandler,
    PostbackPendingService,
    pending_handler,
    postback_pending_service,
)

__all__ = [
    "PendingHandler",
    "PostbackPendingService",
    "pending_handler",
    "postback_pending_service",
]
