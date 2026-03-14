"""
Telegram Bot 全局状态管理

维护 Bot 实例和初始化状态，支持多进程环境
"""
import logging
import threading
from app.core.config import settings

logger = logging.getLogger(__name__)

# ====== Bot 全局状态 ======
# Bot 实例（由 bot_initializer.py 初始化）
bot = None

# Bot 初始化状态标志
bot_initialized = False

# pyTelegramBotAPI 模块可用性
TELEBOT_AVAILABLE = False

# 文件锁相关（多进程环境）
_bot_lock_file = None
_bot_lock_acquired = False


def get_bot_state():
    """
    获取 Bot 当前状态
    
    Returns:
        dict: Bot 状态字典
    """
    return {
        'bot': bot,
        'bot_initialized': bot_initialized,
        'TELEBOT_AVAILABLE': TELEBOT_AVAILABLE,
        'lock_file': _bot_lock_file,
        'lock_acquired': _bot_lock_acquired
    }


def set_bot_state(new_bot, initialized: bool, available: bool):
    """
    设置 Bot 状态
    
    Args:
        new_bot: Bot 实例
        initialized: 是否已初始化
        available: 模块是否可用
    """
    global bot, bot_initialized, TELEBOT_AVAILABLE
    bot = new_bot
    bot_initialized = initialized
    TELEBOT_AVAILABLE = available
    logger.info(f"Bot 状态已更新：initialized={initialized}, available={available}")


def get_bot_status_info():
    """
    获取 Bot 详细状态信息
    
    Returns:
        dict: 包含 Bot 状态信息的字典
    """
    # 检查 Token 是否配置
    token_configured = bool(getattr(settings, 'TELEGRAM_TOKEN', None))
    
    # 检查管理员 Chat ID 是否配置
    admin_configured = bool(getattr(settings, 'TELEGRAM_ADMIN', None))
    
    # 检查轮询线程状态
    bot_thread_alive = False
    for thread in threading.enumerate():
        if thread.name == "TelegramBot":
            bot_thread_alive = thread.is_alive()
            break
    
    # 测试连接
    connection_test = "未测试"
    if bot_initialized and TELEBOT_AVAILABLE and bot:
        try:
            bot.get_me()
            connection_test = "成功"
        except Exception as e:
            connection_test = f"失败: {str(e)}"
    
    return {
        "token_configured": token_configured,
        "admin_configured": admin_configured,
        "bot_thread_alive": bot_thread_alive,
        "connection_test": connection_test
    }
