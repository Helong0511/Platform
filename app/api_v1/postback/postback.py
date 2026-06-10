"""统一 Postback 服务接口
支持多平台的 postback 回调处理

功能说明：
- 接收和处理来自上游平台的 postback 回调
- 查询和管理转化记录（已融合转化日志功能）
- 支持多维度筛选：平台、产品、客户、Click ID、Offer、渠道、广告主、转化状态等
- 提供转化统计、转发日志、诊断工具等功能
- 支持更新转化状态（Approved/Pending）

注意：
- 转化日志功能已融合到此模块，原 /api/v1/conversion-logs 接口已废弃
- 建议使用 /api/v1/postback/conversions 接口进行所有转化记录查询
- 路由实现位于 routes/ 目录；Service 单例经 handlers/__init__.py 统一导出

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
from .routes import router
from .handlers import (
    conversion_handler,
    stats_handler,
    forward_log_handler,
    diagnostic_handler,
    pending_handler,
    duplicate_handler,
    receive_handler
)

__all__ = [
    "router",
    "conversion_handler",
    "stats_handler",
    "forward_log_handler",
    "diagnostic_handler",
    "pending_handler",
    "duplicate_handler",
    "receive_handler"
]
