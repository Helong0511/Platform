"""
Telegram Bot 全局状态管理

维护 Bot 实例和初始化状态，支持多进程环境
"""
import logging

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
