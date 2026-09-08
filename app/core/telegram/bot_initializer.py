"""
Telegram Bot 初始化模块

负责初始化与配置（python-telegram-bot）。
轮询由 polling_manager 创建 Application；此处主要校验 Token / 模块可用性。
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.telegram import bot_state
from app.core.telegram.ptb_runtime import PTB_AVAILABLE

TELEBOT_AVAILABLE = PTB_AVAILABLE
if PTB_AVAILABLE:
    logger.info("python-telegram-bot 模块导入成功")


def initialize_bot():
    """
    初始化 Telegram Bot 状态（在 settings 对象完全初始化后调用）

    Returns:
        tuple: (bot_instance, initialized, available)
    """
    dynamic_available = PTB_AVAILABLE
    if not dynamic_available:
        try:
            import telegram  # noqa: F401

            dynamic_available = True
            logger.info("python-telegram-bot 模块导入成功（动态检查）")
        except ImportError as import_err:
            logger.warning(
                "python-telegram-bot 模块未安装，Telegram Bot 功能将不可用。"
                "请运行：pip install 'python-telegram-bot==22.8'。详情：%s",
                import_err,
            )

    from app.core.telegram.bot_state import set_bot_state, _bot_instance_created
    from app.core.telegram.file_lock import acquire_bot_lock, release_bot_lock
    from app.core.telegram.shared_state import get_shared_state, set_shared_state

    shared_state = get_shared_state()
    bot_initialized_in_state = shared_state.get("bot_initialized", False)
    current_pid_in_state = shared_state.get("current_pid")

    if bot_initialized_in_state and current_pid_in_state:
        try:
            os.kill(current_pid_in_state, 0)
            logger.info(
                f"Bot 已在其他进程（PID:{current_pid_in_state}）中初始化，跳过初始化..."
            )
            return bot_state.bot, bot_state.bot_initialized, bot_state.TELEBOT_AVAILABLE
        except OSError:
            logger.info(
                f"共享状态中的进程（PID:{current_pid_in_state}）未运行，清理过时状态..."
            )
            set_shared_state(
                {
                    "bot_initialized": False,
                    "bot_running": False,
                    "last_start_time": None,
                    "current_pid": None,
                    "bot_username": None,
                }
            )
    elif bot_initialized_in_state and not current_pid_in_state:
        logger.info("共享状态显示已初始化但无进程ID，清理过时状态...")
        set_shared_state(
            {
                "bot_initialized": False,
                "bot_running": False,
                "last_start_time": None,
                "current_pid": None,
                "bot_username": None,
            }
        )

    if _bot_instance_created and bot_state.bot_initialized:
        logger.info("Bot 实例已经创建，跳过初始化...")
        return bot_state.bot, bot_state.bot_initialized, bot_state.TELEBOT_AVAILABLE

    telegram_enabled = getattr(settings, "TELEGRAM_ENABLE", True)
    logger.info(f"Telegram Bot 功能启用状态：{telegram_enabled}")

    if not telegram_enabled:
        logger.info("Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false）")
        set_bot_state(None, False, dynamic_available, new_application=None)
        return None, False, dynamic_available

    if not dynamic_available:
        logger.info("Telegram Bot 功能已禁用（python-telegram-bot 未安装）")
        set_bot_state(None, False, False, new_application=None)
        return None, False, False

    try:
        logger.info("尝试获取 Bot 初始化锁...")
        lock_acquired = acquire_bot_lock()

        if not lock_acquired:
            logger.info("其他进程已初始化 Bot，跳过初始化...")
            set_bot_state(None, False, dynamic_available, new_application=None)
            return None, False, dynamic_available

        try:
            logger.info("正在加载 Telegram token...")
            token = getattr(settings, "TELEGRAM_TOKEN", None) or None
            logger.info(
                f"Telegram token 加载结果：{token[:4]}****" if token else "None"
            )

            if token and isinstance(token, str) and token.strip():
                from app.core.telegram.ptb_runtime import get_send_bot

                send_bot = get_send_bot(
                    token.strip(),
                    connect_timeout=3.0,
                    read_timeout=5.0,
                )
                set_bot_state(send_bot, True, dynamic_available, new_application=None)
                set_shared_state(
                    {
                        "bot_initialized": True,
                        "current_pid": os.getpid(),
                        "bot_running": False,
                        "last_start_time": None,
                        "bot_username": None,
                    }
                )
                logger.info(f"Telegram Bot 初始化成功，token: {token[:4]}****")
                return send_bot, True, dynamic_available

            logger.warning("Telegram token 未设置或为空，Telegram Bot 功能将不可用")
            set_bot_state(None, False, dynamic_available, new_application=None)
            return None, False, dynamic_available
        finally:
            release_bot_lock()
            logger.info("Bot 初始化锁已释放")

    except Exception as err:
        logger.error(f"初始化 Telegram Bot 失败：{err}", exc_info=True)
        set_bot_state(None, False, dynamic_available, new_application=None)
        return None, False, dynamic_available


def get_bot():
    """获取 Bot 实例；未初始化则返回 None。"""
    from app.core.telegram.bot_state import bot

    return bot


def is_bot_available() -> bool:
    """检查 Bot 是否可用。"""
    return (
        bot_state.bot_initialized
        and bot_state.TELEBOT_AVAILABLE
        and (
            bot_state.bot is not None
            or bool(getattr(settings, "TELEGRAM_TOKEN", None))
        )
    )
