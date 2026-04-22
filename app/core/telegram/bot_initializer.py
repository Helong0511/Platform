"""
Telegram Bot 初始化模块

负责初始化和配置 Telegram Bot 实例
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 延迟导入，确保 settings 已完全初始化
from app.core.config import settings

# 尝试导入 telebot 模块
TELEBOT_AVAILABLE = False
try:
    import telebot  # pip3 install --upgrade pyTelegramBotAPI
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
    # 动态检查模块可用性
    try:
        # 使用模块级导入
        import telebot
        dynamic_telebot_available = True
        logger.info("pyTelegramBotAPI 模块导入成功（动态检查）")
    except ImportError as import_err:
        dynamic_telebot_available = False
        logger.warning(
            f"pyTelegramBotAPI 模块未安装，Telegram Bot 功能将不可用。"
            f"请运行：pip install pyTelegramBotAPI"
        )
        logger.warning(f"导入错误详情：{import_err}")
    
    from app.core.telegram.bot_state import set_bot_state, _bot_instance_created
    from app.core.telegram.file_lock import acquire_bot_lock, release_bot_lock
    from app.core.telegram.shared_state import get_shared_state, set_shared_state, update_shared_state
    
    # 检查共享状态
    shared_state = get_shared_state()
    bot_initialized_in_state = shared_state.get("bot_initialized", False)
    current_pid_in_state = shared_state.get("current_pid")
    
    # 验证共享状态中的进程是否真的在运行
    if bot_initialized_in_state and current_pid_in_state:
        try:
            os.kill(current_pid_in_state, 0)
            # 进程在运行，跳过初始化
            logger.info(f"Bot 已在其他进程（PID:{current_pid_in_state}）中初始化，跳过初始化...")
            from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
            return bot, bot_initialized, TELEBOT_AVAILABLE
        except OSError:
            # 进程不在运行，清理过时的状态
            logger.info(f"共享状态中的进程（PID:{current_pid_in_state}）未运行，清理过时状态...")
            set_shared_state({"bot_initialized": False, "bot_running": False, "last_start_time": None, "current_pid": None, "bot_username": None})
            # 继续初始化
    elif bot_initialized_in_state and not current_pid_in_state:
        # 状态文件显示已初始化但无进程ID，清理状态
        logger.info("共享状态显示已初始化但无进程ID，清理过时状态...")
        set_shared_state({"bot_initialized": False, "bot_running": False, "last_start_time": None, "current_pid": None, "bot_username": None})
        # 继续初始化
    
    # 检查 Bot 实例是否已经创建
    if _bot_instance_created:
        logger.info("Bot 实例已经创建，跳过初始化...")
        from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
        return bot, bot_initialized, TELEBOT_AVAILABLE
    
    # 初始化 Telegram Bot（仅在模块可用且启用时）
    telegram_enabled = getattr(settings, 'TELEGRAM_ENABLE', True)
    logger.info(f"Telegram Bot 功能启用状态：{telegram_enabled}")
    
    if not telegram_enabled:
        logger.info("Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）")
        set_bot_state(None, False, dynamic_telebot_available)
        return None, False, dynamic_telebot_available
    
    elif dynamic_telebot_available:
        try:
            # 尝试获取锁，只有获取到锁的进程才能初始化 Bot
            logger.info("尝试获取 Bot 初始化锁...")
            lock_acquired = acquire_bot_lock()
            
            if not lock_acquired:
                logger.info("其他进程已初始化 Bot，跳过初始化...")
                set_bot_state(None, False, dynamic_telebot_available)
                return None, False, dynamic_telebot_available
            
            try:
                logger.info("正在加载 Telegram token...")
                token = getattr(settings, 'TELEGRAM_TOKEN', None) or None
                logger.info(f"Telegram token 加载结果：{token[:4]}****" if token else "None")
                
                if token and isinstance(token, str) and token.strip():
                    # 初始化 Telegram Bot
                    bot_instance = telebot.TeleBot(token=token)
                    set_bot_state(bot_instance, True, dynamic_telebot_available)
                    # 更新共享状态（原子操作，避免竞态条件）
                    set_shared_state({
                        "bot_initialized": True,
                        "current_pid": os.getpid(),
                        "bot_running": False,
                        "last_start_time": None,
                        "bot_username": None
                    })
                    logger.info(f"Telegram Bot 初始化成功，token: {token[:4]}****")
                    return bot_instance, True, dynamic_telebot_available
                else:
                    logger.warning("Telegram token 未设置或为空，Telegram Bot 功能将不可用")
                    set_bot_state(None, False, dynamic_telebot_available)
                    return None, False, dynamic_telebot_available
                    
            finally:
                # 释放锁
                release_bot_lock()
                logger.info("Bot 初始化锁已释放")
                
        except Exception as err:
            logger.error(f"初始化 Telegram Bot 失败：{err}", exc_info=True)
            set_bot_state(None, False, dynamic_telebot_available)
            return None, False, dynamic_telebot_available
    
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


# 初始化 Bot 的函数将在 main.py 中显式调用
# 避免模块导入时执行，防止多进程同时初始化
