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


def _api(chat_id: int, coro):
    """后台线程内走发送互斥，避免与业务通知撞 429。"""
    from app.core.telegram.message_sender import call_telegram_api_throttled

    return call_telegram_api_throttled(coro, chat_id=str(chat_id))


def _process_stats_request(
    period_key: str,
    chat_id: int,
    message_id: int,
):
    """在后台线程中查询统计并更新消息。"""
    from app.core.config import settings
    from app.core.telegram.command_handlers.stats_command import send_stats_menu
    from app.core.telegram.ptb_runtime import build_inline_keyboard, get_send_bot
    from app.core.telegram.stats_period import STATS_PERIOD_LABELS, resolve_stats_date_range
    from app.core.telegram.stats_service import (
        STATS_MENU_CALLBACK,
        build_stats_menu_buttons,
        fetch_stats_sync,
        format_stats_messages,
    )

    token = getattr(settings, "TELEGRAM_TOKEN", None)
    if not token:
        logger.error("[统计回调] TELEGRAM_TOKEN 未配置")
        return
    bot = get_send_bot(str(token).strip())

    try:
        if period_key == STATS_MENU_CALLBACK:
            send_stats_menu(chat_id, message_id=message_id)
            return

        summary = fetch_stats_sync(period_key)
        if not summary:
            _api(
                chat_id,
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ 统计查询失败，请稍后重试。",
                ),
            )
            return

        _, _, period_label = resolve_stats_date_range(period_key)
        messages = format_stats_messages(summary, period_label)
        buttons = build_stats_menu_buttons(include_back=True)
        markup = build_inline_keyboard(buttons)

        _api(
            chat_id,
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=messages[0],
                parse_mode="HTML",
                reply_markup=markup,
            ),
        )
        for extra_text in messages[1:]:
            _api(
                chat_id,
                bot.send_message(
                    chat_id=chat_id,
                    text=extra_text,
                    parse_mode="HTML",
                ),
            )
        logger.info(
            f"[统计回调] 已展示 {STATS_PERIOD_LABELS.get(period_key, period_key)} 统计, chat_id={chat_id}"
        )
    except Exception as exc:
        logger.error(f"[统计回调] 处理失败: {exc}", exc_info=True)
        try:
            _api(
                chat_id,
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ 统计处理出错，请稍后重试。",
                ),
            )
        except Exception:
            pass


async def handle_stats_callbacks(update, context):
    """处理 stats_ 前缀的内联按钮回调。"""
    from app.core.telegram.stats_service import STATS_MENU_CALLBACK

    query = update.callback_query
    if not query or not query.message:
        return

    data = query.data or ""
    if data != STATS_MENU_CALLBACK and data not in VALID_STATS_PERIODS:
        return

    try:
        await query.answer(text="正在查询统计...", show_alert=False)
    except Exception as exc:
        logger.warning(f"[统计回调] 即时确认失败: {exc}")

    thread = threading.Thread(
        target=_process_stats_request,
        args=(data, query.message.chat_id, query.message.message_id),
        daemon=True,
    )
    thread.start()
