"""
菜单回调处理器

处理通用菜单按钮的回调
"""
import logging

logger = logging.getLogger(__name__)


def handle_menu_callbacks(call):
    """
    处理菜单按钮回调
    
    Args:
        call: Telegram 回调查询对象
    """
    from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
    from app.core.utils import get_app_now
    
    def _check_bot_available() -> bool:
        """检查 Bot 是否可用"""
        return bot_initialized and TELEBOT_AVAILABLE and bot is not None
    
    if not _check_bot_available():
        logger.error("[回调查询处理器] Bot 未初始化，无法处理菜单回调")
        return
    
    try:
        if call.data == "View":
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="你点击了查看按钮"
            )
        elif call.data == "clock":
            current_time = get_app_now()
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"打卡成功！时间：{current_time.strftime('%Y-%m-%d %H:%M:%S')}（时区：Asia/Shanghai）"
            )
    except Exception as e:
        logger.error(f"处理菜单回调失败：{str(e)}", exc_info=True)
