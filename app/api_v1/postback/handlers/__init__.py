"""Postback 各业务子域的 Handler 适配层统一导出。

每个 handler 模块将 app.services.cpl 下对应 Service 的实例重新导出，
供 routes.py 注入路由依赖，保持 API 层与 Service 层的解耦。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。"""
from .conversion_handler import conversion_handler
from .stats_handler import stats_handler
from .forward_log_handler import forward_log_handler
from .diagnostic_handler import diagnostic_handler
from .pending_handler import pending_handler
from .duplicate_handler import duplicate_handler
from .receive_handler import receive_handler

__all__ = [
    "conversion_handler",
    "stats_handler",
    "forward_log_handler",
    "diagnostic_handler",
    "pending_handler",
    "duplicate_handler",
    "receive_handler"
]
