"""重复转化 API 适配层。

导出 PostbackDuplicateService 实例，供管理端查询与处理
因 click_id/transaction_id 重复触发的转化记录。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
from app.services.cpl.postback_duplicate_service import (
    DuplicateHandler,
    PostbackDuplicateService,
    duplicate_handler,
    postback_duplicate_service,
)

__all__ = [
    "DuplicateHandler",
    "PostbackDuplicateService",
    "duplicate_handler",
    "postback_duplicate_service",
]
