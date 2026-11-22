"""
/id 命令处理器

返回聊天 ID（支持私聊和群组，python-telegram-bot）。
"""
import logging

from app.core.telegram import send_telegram_message_async
from app.core.telegram_utils import escape_html, mask_telegram_chat_id

logger = logging.getLogger(__name__)


async def get_chat_id(update, context):
    """处理 /id：返回聊天 ID。"""
    message = update.effective_message
    user = update.effective_user
    if not message or not message.chat:
        return

    chat = message.chat
    chat_type = chat.type if hasattr(chat, "type") else "未知"
    is_group = chat_type in ["group", "supergroup"]

    bot_mentioned = False
    bot_username = None
    if is_group:
        try:
            bot_info = await context.bot.get_me()
            bot_username = bot_info.username if bot_info else None
            if bot_username:
                text = message.text or ""
                if f"@{bot_username}" in text:
                    bot_mentioned = True
                if message.entities:
                    for entity in message.entities:
                        if entity.type == "mention":
                            mention_text = text[entity.offset : entity.offset + entity.length]
                            if mention_text == f"@{bot_username}":
                                bot_mentioned = True
                                break
        except Exception as e:
            logger.warning("获取 Bot 信息失败；error_type=%s", type(e).__name__)

    logger.info(
        "[命令处理器] 收到 /id 命令，user_id=%s chat_id=%s chat_type=%s bot_mentioned=%s",
        mask_telegram_chat_id(getattr(user, "id", None)),
        mask_telegram_chat_id(chat.id),
        chat_type,
        bot_mentioned,
    )

    if is_group and not bot_mentioned and bot_username:
        logger.warning(
            f"[命令处理器] ⚠️ 群组中的命令没有 @{bot_username}，"
            f"可能无法响应（Telegram 隐私模式）"
        )

    response_lines = [
        f"💬 Chat ID: <code>{chat.id}</code>",
        f"👤 User ID: <code>{user.id if user else 'N/A'}</code>",
        f"💬 Chat Type: {chat_type}",
    ]

    if is_group:
        response_lines.append(f"👥 Group Title: {escape_html(chat.title or 'N/A')}")
        if bot_username:
            response_lines.append(f"🤖 Bot Username: @{bot_username}")

    try:
        sent = await send_telegram_message_async(
            chat.id,
            "\n".join(response_lines),
            parse_mode="HTML",
            reply_to_message_id=message.message_id,
        )
        if not sent:
            logger.warning(
                "[命令处理器] Chat ID 回复发送失败，chat_id=%s",
                mask_telegram_chat_id(chat.id),
            )
            return
        logger.info(
            "[命令处理器] 已发送 Chat ID 到：%s",
            mask_telegram_chat_id(chat.id),
        )
    except Exception as e:
        from app.core.telegram.command_handlers._reply_errors import log_command_reply_failure

        log_command_reply_failure("id", chat.id, e)
