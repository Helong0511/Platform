"""
Telegram Bot 初始化模块

负责初始化和配置 Telegram Bot 实例
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 延迟导入，确保 settings 已完全初始化
from app.core.config import settings

# 尝试导入 telebot 模块
TELEBOT_AVAILABLE = False
try:
    import telebot  # pip3 install --upgrade pyTelegramBotAPI
    from telebot import types
    from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
    TELEBOT_AVAILABLE = True
    logger.info("pyTelegramBotAPI 模块导入成功")
except ImportError as import_err:
    TELEBOT_AVAILABLE = False
    logger.warning(
        f"pyTelegramBotAPI 模块未安装，Telegram Bot 功能将不可用。"
        f"请运行：pip install pyTelegramBotAPI"
    )
    logger.warning(f"导入错误详情：{import_err}")


def initialize_bot():
    """
    初始化 Telegram Bot（在 settings 对象完全初始化后调用）
    
    Returns:
        tuple: (bot_instance, initialized, available)
    """
    from app.core.telegram.bot_state import set_bot_state, _bot_instance_created, TELEBOT_AVAILABLE
    from app.core.telegram.file_lock import acquire_bot_lock, release_bot_lock
    
    # 检查 Bot 实例是否已经创建
    if _bot_instance_created:
        logger.info("Bot 实例已经创建，跳过初始化...")
        from app.core.telegram.bot_state import bot, bot_initialized
        return bot, bot_initialized, TELEBOT_AVAILABLE
    
    # 初始化 Telegram Bot（仅在模块可用且启用时）
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    logger.info(f"Telegram Bot 功能启用状态：{telegram_enabled}")
    
    if not telegram_enabled:
        logger.info("Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）")
        set_bot_state(None, False, TELEBOT_AVAILABLE)
        return None, False, TELEBOT_AVAILABLE
    
    elif TELEBOT_AVAILABLE:
        try:
            # 尝试获取锁，只有获取到锁的进程才能初始化 Bot
            logger.info("尝试获取 Bot 初始化锁...")
            lock_acquired = acquire_bot_lock()
            
            if not lock_acquired:
                logger.info("其他进程已初始化 Bot，跳过初始化...")
                set_bot_state(None, False, TELEBOT_AVAILABLE)
                return None, False, TELEBOT_AVAILABLE
            
            try:
                logger.info("正在加载 Telegram token...")
                token = getattr(settings, 'TELEGRAM_TOKEN', None) or None
                logger.info(f"Telegram token 加载结果：{token[:4]}****" if token else "None")
                
                if token and isinstance(token, str) and token.strip():
                    # 初始化 Telegram Bot
                    bot_instance = telebot.TeleBot(token=token)
                    set_bot_state(bot_instance, True, TELEBOT_AVAILABLE)
                    logger.info(f"Telegram Bot 初始化成功，token: {token[:4]}****")
                    return bot_instance, True, TELEBOT_AVAILABLE
                else:
                    logger.warning("Telegram token 未设置或为空，Telegram Bot 功能将不可用")
                    set_bot_state(None, False, TELEBOT_AVAILABLE)
                    return None, False, TELEBOT_AVAILABLE
                    
            finally:
                # 释放锁
                release_bot_lock()
                logger.info("Bot 初始化锁已释放")
                
        except Exception as err:
            logger.error(f"初始化 Telegram Bot 失败：{err}", exc_info=True)
            set_bot_state(None, False, TELEBOT_AVAILABLE)
            return None, False, TELEBOT_AVAILABLE
    
    else:
        logger.info("Telegram Bot 功能已禁用（pyTelegramBotAPI 未安装）")
        set_bot_state(None, False, False)
        return None, False, False


def get_bot():
    """
    获取 Bot 实例
    
    Returns:
        Bot 实例，如果未初始化则返回 None
    """
    from app.core.telegram.bot_state import bot
    return bot


def is_bot_available() -> bool:
    """
    检查 Bot 是否可用
    
    Returns:
        bool: Bot 是否可用
    """
    from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
    return bot_initialized and TELEBOT_AVAILABLE and bot is not None


# 自动初始化 Bot
# 注意：这会在模块导入时执行，确保 settings 已完全初始化
bot_instance, initialized, available = initialize_bot()
