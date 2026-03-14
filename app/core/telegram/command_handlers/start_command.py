"""
/start 命令处理器

处理用户首次启动 Bot 的欢迎消息
"""
import logging
from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE

logger = logging.getLogger(__name__)


def _check_bot_available() -> bool:
    """检查 Bot 是否可用"""
    return bot_initialized and TELEBOT_AVAILABLE and bot is not None


@bot.message_handler(commands=['start'])
def cmd_start(message):
        """
        处理 /start 命令：发送欢迎消息
        
        Args:
            message: Telegram 消息对象
        """
        if not _check_bot_available():
            logger.error("[命令处理器] Bot 未初始化，无法处理 /start 命令")
            return
        
        user_name = message.from_user.first_name or '用户'
        welcome_text = (
            f"👋 你好，{user_name}！\n\n"
            f"我是广告管理平台的 Bot，可以帮助你：\n"
            f"• 接收转化通知\n"
            f"• 查看系统状态\n"
            f"• 管理 Postback 待确认项\n\n"
            f"使用 /help 查看所有可用命令。"
        )
        
        try:
            bot.send_message(
                chat_id=message.chat.id,
                text=welcome_text,
                parse_mode='HTML'
            )
            logger.info(f"[命令处理器] 已发送欢迎消息到：{message.chat.id}")
        except Exception as e:
            logger.error(f"[命令处理器] 发送欢迎消息失败：{e}")
