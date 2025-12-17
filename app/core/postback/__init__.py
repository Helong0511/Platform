"""
Postback 核心处理模块
统一管理各平台的 postback 回调处理
"""
from app.core.postback.processor import PostbackProcessor
from app.core.postback.handlers import PostbackHandler, register_handler, get_handler
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.notifier import PostbackNotifier

__all__ = [
    "PostbackProcessor",
    "PostbackHandler",
    "register_handler",
    "get_handler",
    "PostbackForwarder",
    "PostbackNotifier",
]

