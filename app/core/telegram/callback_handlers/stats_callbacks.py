"""
统计菜单回调处理器

处理 stats_* 内联按钮：展示各周期转化统计或返回菜单。
"""
import logging
import threading

logger = logging.getLogger(__name__)

VALID_STATS_PERIODS = frozenset({
    "stats_yesterday",
    "stats_this_week",
    "stats_last_week",
    "stats_this_month",
})


def _process_stats_request(
    period_key: str,
    chat_id: int,
    message_id: int,
):
    """在后台线程中查询统计并更新消息。"""
    from app.core.telegram.bot_state import bot
    from app.core.telegram.command_handlers.stats_command import send_stats_menu
    from app.core.telegram.stats_period import STATS_PERIOD_LABELS, resolve_stats_date_range
    from app.core.telegram.stats_service import (
        STATS_MENU_CALLBACK,
        build_stats_menu_buttons,
        fetch_stats_sync,
        format_stats_messages,
    )

    try:
        if period_key == STATS_MENU_CALLBACK:
            send_stats_menu(chat_id, message_id=message_id)
            return

        summary = fetch_stats_sync(period_key)
        if not summary:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ 统计查询失败，请稍后重试。",
            )
            return

        _, _, period_label = resolve_stats_date_range(period_key)
        messages = format_stats_messages(summary, period_label)
        buttons = build_stats_menu_buttons(include_back=True)

        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

        markup = InlineKeyboardMarkup()
        for row in buttons:
            markup.row(*[
                InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])
                for btn in row
            ])

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=messages[0],
            parse_mode="HTML",
            reply_markup=markup,
        )
        for extra_text in messages[1:]:
            bot.send_message(
                chat_id=chat_id,
                text=extra_text,
                parse_mode="HTML",
            )
        logger.info(
            f"[统计回调] 已展示 {STATS_PERIOD_LABELS.get(period_key, period_key)} 统计, chat_id={chat_id}"
        )
    except Exception as exc:
        logger.error(f"[统计回调] 处理失败: {exc}", exc_info=True)
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ 统计处理出错，请稍后重试。",
            )
        except Exception:
            pass


def handle_stats_callbacks(call):
    """处理 stats_ 前缀的内联按钮回调。"""
    from app.core.telegram.bot_state import bot_initialized, TELEBOT_AVAILABLE, bot
    from app.core.telegram.stats_service import STATS_MENU_CALLBACK

    if not (bot_initialized and TELEBOT_AVAILABLE and bot):
        logger.error("[统计回调] Bot 未初始化")
        return

    data = call.data or ""
    if data != STATS_MENU_CALLBACK and data not in VALID_STATS_PERIODS:
        return

    try:
        bot.answer_callback_query(
            callback_query_id=call.id,
            text="正在查询统计...",
            show_alert=False,
        )
    except Exception as exc:
        logger.warning(f"[统计回调] 即时确认失败: {exc}")

    thread = threading.Thread(
        target=_process_stats_request,
        args=(data, call.message.chat.id, call.message.message_id),
        daemon=True,
    )
    thread.start()
