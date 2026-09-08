"""
Telegram Bot 模块

提供 Telegram Bot 的完整功能，包括：
- Bot 初始化和状态管理
- 命令处理器（/start, /id, /help 等）
- 回调处理器（内联按钮）
- 消息发送和通知
- 文件锁管理（多进程环境）
"""

from app.core.telegram.bot_initializer import initialize_bot, get_bot, is_bot_available
from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE, get_bot_status_info
from app.core.telegram.message_sender import (
    is_telegram_enabled,
    send_telegram_message,
    send_telegram_message_async,
    send_telegram_notify_async,
    send_telegram_message_with_buttons,
    send_admin_notification
)
from app.core.telegram.notification_templates import (
    ConversionNotificationTemplate,
    SystemNotificationTemplate,
    StatisticsNotificationTemplate
)

__all__ = [
    # Bot 初始化
    'initialize_bot',
    'get_bot',
    'is_bot_available',
    
    # Bot 状态（向后兼容）
    'bot',
    'bot_initialized',
    'TELEBOT_AVAILABLE',
    'get_bot_status_info',
    
    # 消息发送
    'is_telegram_enabled',
    'send_telegram_message',
    'send_telegram_message_async',
    'send_telegram_notify_async',
    'send_telegram_message_with_buttons',
    'send_admin_notification',
    
    # 通知模板
    'ConversionNotificationTemplate',
    'SystemNotificationTemplate',
    'StatisticsNotificationTemplate',
]
