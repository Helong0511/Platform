"""
Telegram Bot 全局状态管理

维护 Bot / Application 实例和初始化状态，支持多进程环境。
TELEBOT_AVAILABLE 为历史命名，现表示 python-telegram-bot 是否可用。
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ====== Bot 全局状态 ======
# 轮询用 Application（由 polling_manager 创建）；发送优先走 ptb_runtime 发送 Bot
application: Any = None

# Bot 实例（通常为 application.bot；未轮询时可为 None）
bot = None

# Bot 初始化状态标志
bot_initialized = False

# python-telegram-bot 模块可用性（历史名 TELEBOT_AVAILABLE，保持兼容）
TELEBOT_AVAILABLE = False

# 文件锁相关（多进程环境）
_bot_lock_file = None
_bot_lock_acquired = False

# 标记 Bot 实例是否已经创建（用于多进程环境）
_bot_instance_created = False

# 连接探测：短超时 + 结果缓存，避免管理页卡在 api.telegram.org
_CONNECTION_PROBE_TIMEOUT_SEC = 3.0
_CONNECTION_CACHE_TTL_SEC = 60.0
_CONNECTION_FAIL_CACHE_TTL_SEC = 15.0
_connection_cache: dict = {"result": None, "ts": 0.0}
_probe_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tg-probe")


def get_bot_state():
    """
    获取 Bot 当前状态

    Returns:
        dict: Bot 状态字典
    """
    return {
        "bot": bot,
        "application": application,
        "bot_initialized": bot_initialized,
        "TELEBOT_AVAILABLE": TELEBOT_AVAILABLE,
        "lock_file": _bot_lock_file,
        "lock_acquired": _bot_lock_acquired,
    }


def set_bot_state(
    new_bot,
    initialized: bool,
    available: bool,
    new_application: Optional[Any] = None,
):
    """
    设置 Bot 状态

    Args:
        new_bot: Bot 实例
        initialized: 是否已初始化
        available: 模块是否可用
        new_application: PTB Application（可选）
    """
    global bot, bot_initialized, TELEBOT_AVAILABLE, _bot_instance_created, application
    bot = new_bot
    bot_initialized = initialized
    TELEBOT_AVAILABLE = available
    if new_application is not None or new_bot is None:
        application = new_application

    if new_bot:
        _bot_instance_created = True
        logger.info("Bot 实例已创建，标记为已创建状态")

    logger.info(
        "Bot 状态已更新：initialized=%s, available=%s, has_application=%s",
        initialized,
        available,
        application is not None,
    )


def _probe_telegram_connection() -> str:
    """短超时探测 get_me，失败/超时不阻塞过久。"""
    if not (bot_initialized and TELEBOT_AVAILABLE):
        return "未测试"
    token = getattr(settings, "TELEGRAM_TOKEN", None)
    if not token or not str(token).strip():
        return "未测试"
    try:
        from app.core.telegram.ptb_runtime import get_send_bot, run_on_send_loop

        send_bot = get_send_bot(str(token).strip(), connect_timeout=3.0, read_timeout=5.0)
        future = _probe_executor.submit(
            lambda: run_on_send_loop(send_bot.get_me(), timeout=_CONNECTION_PROBE_TIMEOUT_SEC)
        )
        future.result(timeout=_CONNECTION_PROBE_TIMEOUT_SEC + 1.0)
        return "成功"
    except FuturesTimeoutError:
        return f"超时(>{int(_CONNECTION_PROBE_TIMEOUT_SEC)}s，本地网络可能无法访问 Telegram)"
    except Exception as e:
        return f"失败: {str(e)}"


def get_bot_status_info():
    """
    获取 Bot 详细状态信息

    Returns:
        dict: 包含 Bot 状态信息的字典
    """
    token_configured = bool(getattr(settings, "TELEGRAM_TOKEN", None))
    admin_configured = bool(getattr(settings, "TELEGRAM_ADMIN", None))

    bot_thread_alive = False
    for thread in threading.enumerate():
        if thread.name == "TelegramBot":
            bot_thread_alive = thread.is_alive()
            break

    connection_test = "未测试"
    now = time.monotonic()
    cached = _connection_cache.get("result")
    cached_ts = float(_connection_cache.get("ts") or 0.0)
    ttl = (
        _CONNECTION_CACHE_TTL_SEC
        if cached == "成功"
        else _CONNECTION_FAIL_CACHE_TTL_SEC
    )
    if cached is not None and (now - cached_ts) < ttl:
        connection_test = cached
    elif bot_initialized and TELEBOT_AVAILABLE:
        connection_test = _probe_telegram_connection()
        _connection_cache["result"] = connection_test
        _connection_cache["ts"] = now

    return {
        "token_configured": token_configured,
        "admin_configured": admin_configured,
        "bot_thread_alive": bot_thread_alive,
        "connection_test": connection_test,
    }
