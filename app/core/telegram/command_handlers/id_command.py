"""
/id 命令处理器

返回聊天 ID（支持私聊和群组）
"""
import logging
from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE

logger = logging.getLogger(__name__)


def _check_bot_available() -> bool:
    """检查 Bot 是否可用"""
    return bot_initialized and TELEBOT_AVAILABLE and bot is not None


@bot.message_handler(commands=['id'])
def get_chat_id(message):
        """
        处理 /id 命令：返回聊天 ID（支持私聊和群组）
        
        Args:
            message: Telegram 消息对象
        """
        chat_type = message.chat.type if hasattr(message.chat, 'type') else '未知'
        is_group = chat_type in ['group', 'supergroup']
        
        # 检查群组中是否包含 Bot 的提及
        bot_mentioned = False
        bot_username = None
        if is_group:
            try:
                bot_info = bot.get_me()
                bot_username = bot_info.username if bot_info else None
                if bot_username:
                    text = message.text or ''
                    if f'@{bot_username}' in text:
                        bot_mentioned = True
                    # 检查 entities
                    if hasattr(message, 'entities') and message.entities:
                        for entity in message.entities:
                            if entity.type == 'mention':
                                mention_text = text[entity.offset:entity.offset + entity.length]
                                if mention_text == f'@{bot_username}':
                                    bot_mentioned = True
                                    break
            except Exception as e:
                logger.warning(f"获取 Bot 信息失败：{e}")
        
        logger.info(
            f"[命令处理器] ✅✅✅ 收到 /id 命令，来自用户："
            f"{message.from_user.username or message.from_user.first_name or '未知'} "
            f"(Chat ID: {message.chat.id}, Chat Type: {chat_type}, Bot Mentioned: {bot_mentioned})"
        )
        
        if not _check_bot_available():
            logger.error("[命令处理器] Bot 未初始化，无法处理消息")
            return
        
        # 在群组中，如果没有 @botname，记录警告（但继续处理）
        if is_group and not bot_mentioned and bot_username:
            logger.warning(
                f"[命令处理器] ⚠️ 群组中的命令没有 @{bot_username}，"
                f"可能无法响应（Telegram 隐私模式）"
            )
            logger.info(
                f"[命令处理器] 💡 提示：在群组中使用命令时，请使用 /id@{bot_username} "
                f"格式，或直接 @{bot_username} 后发送命令"
            )
        
        # 构建响应消息
        response_lines = [
            f"💬 Chat ID: <code>{message.chat.id}</code>",
            f"👤 User ID: <code>{message.from_user.id}</code>",
            f"💬 Chat Type: {chat_type}",
        ]
        
        if is_group:
            response_lines.append(f"👥 Group Title: {message.chat.title or 'N/A'}")
            if bot_username:
                response_lines.append(f"🤖 Bot Username: @{bot_username}")
        
        response_text = '\n'.join(response_lines)
        
        # 发送响应
        try:
            bot.send_message(
                chat_id=message.chat.id,
                text=response_text,
                parse_mode='HTML',
                reply_to_message_id=message.message_id
            )
            logger.info(f"[命令处理器] 已发送 Chat ID 到：{message.chat.id}")
        except Exception as e:
            logger.error(f"[命令处理器] 发送消息失败：{e}")
