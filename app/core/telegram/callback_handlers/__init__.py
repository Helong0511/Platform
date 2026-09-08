"""
Telegram Bot 回调处理器

由 polling_manager.register_handlers 显式注册到 Application。
"""
from app.core.telegram.callback_handlers.postback_approval import handle_postback_approval
from app.core.telegram.callback_handlers.menu_callbacks import handle_menu_callbacks
from app.core.telegram.callback_handlers.stats_callbacks import handle_stats_callbacks

__all__ = [
    "handle_postback_approval",
    "handle_menu_callbacks",
    "handle_stats_callbacks",
]
