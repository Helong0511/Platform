"""
/help 命令处理器

显示 Bot 可用命令列表
"""
import logging

logger = logging.getLogger(__name__)


def cmd_help(message):
    """
    处理 /help 命令：显示帮助信息
    
    Args:
        message: Telegram 消息对象
    """
    from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
    
    def _check_bot_available() -> bool:
        """检查 Bot 是否可用"""
        return bot_initialized and TELEBOT_AVAILABLE and bot is not None
    
    if not _check_bot_available():
        logger.error("[命令处理器] Bot 未初始化，无法处理 /help 命令")
        return
    
    help_text = (
        "📖 **可用命令：**\n\n"
        "• /start - 启动 Bot\n"
        "• /help - 显示帮助信息\n"
        "• /stats - 转化统计（昨天/本周/上周/本月）\n"
        "• /id - 获取聊天 ID\n\n"
        "🔔 **通知类型：**\n"
        "• 转化通知 - 实时接收转化数据\n"
        "• 系统告警 - 转发失败、系统错误等\n"
        "• 定时统计 - 小时/日报表\n\n"
        "💡 **提示：**\n"
        "在群组中使用命令时，请 @Bot 名称以确保 Bot 能收到消息。"
    )
    
    try:
        bot.send_message(
            chat_id=message.chat.id,
            text=help_text,
            parse_mode='Markdown'
        )
        logger.info(f"[命令处理器] 已发送帮助信息到：{message.chat.id}")
    except Exception as e:
        logger.error(f"[命令处理器] 发送帮助信息失败：{e}")
