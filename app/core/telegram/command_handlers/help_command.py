"""
/help 命令处理器

显示 Bot 可用命令列表（python-telegram-bot）。
"""
import logging

logger = logging.getLogger(__name__)


async def cmd_help(update, context):
    """处理 /help：显示帮助信息。"""
    message = update.effective_message
    if not message:
        return

    # 使用 HTML：Telegram 旧版 Markdown 不支持双星号加粗，会导致整条发送失败
    help_text = (
        "📖 <b>可用命令：</b>\n\n"
        "• /start - 启动 Bot\n"
        "• /help - 显示帮助信息\n"
        "• /stats - 广告数据统计（昨天/本周/上周/本月）\n"
        "• /id - 获取聊天 ID\n\n"
        "🔔 <b>通知类型：</b>\n"
        "• 转化通知 - 实时接收转化数据\n"
        "• 系统告警 - 转发失败、系统错误等\n"
        "• 定时统计 - 小时/日报表\n\n"
        "💡 <b>提示：</b>\n"
        "在群组中使用命令时，请 @Bot 名称以确保 Bot 能收到消息。"
    )

    try:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=help_text,
            parse_mode="HTML",
        )
        logger.info(f"[命令处理器] 已发送帮助信息到：{message.chat_id}")
    except Exception as e:
        from app.core.telegram.command_handlers._reply_errors import log_command_reply_failure

        log_command_reply_failure("help", message.chat_id, e)
