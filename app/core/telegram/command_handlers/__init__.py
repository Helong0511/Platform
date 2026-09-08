"""
Telegram Bot 命令处理器

由 polling_manager.register_handlers 显式注册到 Application。
"""
from app.core.telegram.command_handlers.id_command import get_chat_id
from app.core.telegram.command_handlers.start_command import cmd_start
from app.core.telegram.command_handlers.help_command import cmd_help
from app.core.telegram.command_handlers.stats_command import cmd_stats

__all__ = [
    "get_chat_id",
    "cmd_start",
    "cmd_help",
    "cmd_stats",
]
