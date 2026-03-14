"""
Telegram Bot 回调处理器

注册所有回调处理器（内联按钮点击）
"""
from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE

# 始终导入回调处理器（无论 bot 是否已初始化）
# 装饰器会在模块导入时自动注册到 bot
from app.core.telegram.callback_handlers.postback_approval import handle_postback_approval
from app.core.telegram.callback_handlers.menu_callbacks import handle_menu_callbacks

__all__ = [
    'handle_postback_approval',
    'handle_menu_callbacks'
]
