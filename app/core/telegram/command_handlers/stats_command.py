"""
/stats 命令处理器

展示转化统计周期选择菜单（昨天、本周、上周、本月）。
"""
import logging

logger = logging.getLogger(__name__)

STATS_MENU_TEXT = (
    "📊 <b>广告数据统计</b>\n\n"
    "请选择统计周期：\n"
    "• 昨天 — 昨日全天\n"
    "• 本周 — 本周一至今天\n"
    "• 上周 — 上周一至上周日\n"
    "• 本月 — 本月 1 日至今天\n\n"
    "指标含：请求/匹配/展示/点击、覆盖率、可见率、CPC、eCPM、收益等\n"
    "并按每个产品分别展示上述指标"
)


def send_stats_menu(chat_id: int, message_id: int | None = None) -> bool:
    """
    发送或编辑统计周期选择菜单。

    Args:
        chat_id: 聊天 ID
        message_id: 若提供则编辑该消息，否则发送新消息

    Returns:
        是否成功
    """
    from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
    from app.core.telegram.message_sender import send_telegram_message_with_buttons
    from app.core.telegram.stats_service import build_stats_menu_buttons

    if not (bot_initialized and TELEBOT_AVAILABLE and bot):
        logger.error("[命令处理器] Bot 未初始化，无法展示统计菜单")
        return False

    buttons = build_stats_menu_buttons(include_back=False)

    try:
        if message_id:
            from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

            keyboard = []
            for row in buttons:
                keyboard.append([
                    InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])
                    for btn in row
                ])
            markup = InlineKeyboardMarkup()
            for row in keyboard:
                markup.row(*row)

            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=STATS_MENU_TEXT,
                parse_mode="HTML",
                reply_markup=markup,
            )
        else:
            send_telegram_message_with_buttons(
                chat_id=str(chat_id),
                message=STATS_MENU_TEXT,
                buttons=buttons,
                parse_mode="HTML",
            )
        return True
    except Exception as exc:
        logger.error(f"[命令处理器] 展示统计菜单失败: {exc}", exc_info=True)
        return False


def cmd_stats(message):
    """处理 /stats 命令。"""
    send_stats_menu(message.chat.id)
