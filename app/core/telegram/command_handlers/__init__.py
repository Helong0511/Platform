"""
Telegram Bot 命令处理器

注册所有命令处理器（/start, /id, /help 等）
"""
from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE

# 导入所有命令处理器（会在导入时自动注册到 bot）
if bot_initialized and TELEBOT_AVAILABLE:
    from app.core.telegram.command_handlers.id_command import get_chat_id
    from app.core.telegram.command_handlers.start_command import cmd_start
    from app.core.telegram.command_handlers.help_command import cmd_help

__all__ = [
    'get_chat_id',
    'cmd_start',
    'cmd_help'
]
