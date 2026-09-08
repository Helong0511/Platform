"""
菜单回调处理器

处理通用菜单按钮的回调（python-telegram-bot）。
"""
import logging

logger = logging.getLogger(__name__)


async def handle_menu_callbacks(update, context):
    """处理菜单按钮回调。"""
    query = update.callback_query
    if not query or not query.message:
        return

    from app.core.utils import get_app_now

    try:
        await query.answer()
    except Exception as exc:
        logger.warning("菜单回调 answer 失败: %s", exc)

    try:
        if query.data == "View":
            await query.edit_message_text(text="你点击了查看按钮")
        elif query.data == "clock":
            current_time = get_app_now()
            await query.edit_message_text(
                text=(
                    f"打卡成功！时间：{current_time.strftime('%Y-%m-%d %H:%M:%S')}"
                    f"（时区：Asia/Shanghai）"
                )
            )
    except Exception as e:
        logger.error(f"处理菜单回调失败：{str(e)}", exc_info=True)
