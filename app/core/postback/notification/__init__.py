"""Postback 通知子模块"""
from app.core.postback.notification.config_helpers import (
    should_notify,
    get_notification_channels,
    get_client_info,
    get_product_name,
    detect_notification_channel,
)
from app.core.postback.notification.message_builder import (
    build_notification_message,
    build_batch_notification_message,
)
from app.core.postback.notification.sender import (
    send_notification_async,
    send_to_address,
    send_webhook_notification,
    send_to_channel,
)

__all__ = [
    "should_notify",
    "get_notification_channels",
    "get_client_info",
    "get_product_name",
    "detect_notification_channel",
    "build_notification_message",
    "build_batch_notification_message",
    "send_notification_async",
    "send_to_address",
    "send_webhook_notification",
    "send_to_channel",
]
