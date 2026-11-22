"""
/start 命令处理器

处理用户首次启动 Bot 的欢迎消息（python-telegram-bot）。
"""
import logging

from app.core.telegram import send_telegram_message_async
from app.core.telegram_utils import escape_html, mask_telegram_chat_id

logger = logging.getLogger(__name__)


async def cmd_start(update, context):
    """处理 /start：发送欢迎消息并展示统计菜单。"""
    import asyncio

    message = update.effective_message
    user = update.effective_user
    if not message:
        return

    user_name = escape_html((user.first_name if user else None) or "用户")
    welcome_text = (
        f"👋 你好，{user_name}！\n\n"
        f"我是广告管理平台的 Bot，可以帮助你：\n"
        f"• 接收转化通知\n"
        f"• 查看广告数据统计\n"
        f"• 管理 Postback 待确认项\n\n"
        f"使用 /stats 查看统计，或 /help 查看所有命令。"
    )

    try:
        from app.core.telegram.command_handlers.stats_command import send_stats_menu

        sent = await send_telegram_message_async(
            message.chat_id,
            welcome_text,
            parse_mode="HTML",
        )
        if not sent:
            logger.warning(
                "[命令处理器] 欢迎消息发送失败，chat_id=%s",
                mask_telegram_chat_id(message.chat_id),
            )
            return
        await asyncio.to_thread(send_stats_menu, message.chat_id)
        logger.info(
            "[命令处理器] 已发送欢迎消息到：%s",
            mask_telegram_chat_id(message.chat_id),
        )
    except Exception as e:
        from app.core.telegram.command_handlers._reply_errors import log_command_reply_failure

        log_command_reply_failure("start", message.chat_id, e)
