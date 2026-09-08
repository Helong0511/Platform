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
    from app.core.telegram.message_sender import send_telegram_message_with_buttons
    from app.core.telegram.ptb_runtime import (
        PTB_AVAILABLE,
        build_inline_keyboard,
        get_send_bot,
    )
    from app.core.telegram.stats_service import build_stats_menu_buttons
    from app.core.config import settings

    if not PTB_AVAILABLE:
        logger.error("[命令处理器] python-telegram-bot 未安装，无法展示统计菜单")
        return False

    buttons = build_stats_menu_buttons(include_back=False)

    try:
        if message_id:
            token = getattr(settings, "TELEGRAM_TOKEN", None)
            if not token:
                return False
            bot = get_send_bot(str(token).strip())
            markup = build_inline_keyboard(buttons)
            from app.core.telegram.message_sender import call_telegram_api_throttled

            call_telegram_api_throttled(
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=STATS_MENU_TEXT,
                    parse_mode="HTML",
                    reply_markup=markup,
                ),
                chat_id=str(chat_id),
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


async def cmd_stats(update, context):
    """处理 /stats 命令。"""
    import asyncio

    message = update.effective_message
    if not message:
        return
    ok = await asyncio.to_thread(send_stats_menu, message.chat_id)
    if not ok:
        from app.core.telegram.command_handlers._reply_errors import log_command_reply_failure

        log_command_reply_failure(
            "stats",
            message.chat_id,
            RuntimeError("send_stats_menu 返回 False（详见上方展示统计菜单失败日志）"),
        )
