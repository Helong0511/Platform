"""
Telegram Bot 命令处理器

注册所有命令处理器（/start, /id, /help 等）
"""
from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE

# 始终导入命令处理器（无论 bot 是否已初始化）
# 装饰器会在模块导入时自动注册到 bot
from app.core.telegram.command_handlers.id_command import get_chat_id
from app.core.telegram.command_handlers.start_command import cmd_start
from app.core.telegram.command_handlers.help_command import cmd_help

__all__ = [
    'get_chat_id',
    'cmd_start',
    'cmd_help'
]
