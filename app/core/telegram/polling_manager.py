"""
Telegram Bot 轮询管理模块

使用 python-telegram-bot Application.run_polling 做长轮询（守护线程）。
"""
import asyncio
import os
import time
import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

from app.core.telegram.file_lock import acquire_bot_lock, release_bot_lock
from app.core.telegram.shared_state import (
    get_shared_state,
    set_shared_state,
    is_bot_running,
)
from app.core.config import settings
from app.core.telegram.polling_exception_handler import (
    is_telegram_conflict_error,
    is_transient_telegram_network_error,
)
from app.core.telegram.ptb_runtime import PTB_AVAILABLE

_handlers_registered = False
_bot_started = False
_active_application = None
_polling_loop: Optional[asyncio.AbstractEventLoop] = None

# PTB 的 getUpdates 使用独立 HTTPXRequest；默认 read_timeout=5s，
# 必须大于 Telegram 长轮询 timeout=10s，并留出网络/调度余量。
POLLING_LONG_POLL_TIMEOUT_SECONDS = 10.0
POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS = 65.0
POLLING_BOOTSTRAP_RETRIES = 3


def _build_polling_application(token: str):
    """构建 PTB Application，并显式配置 getUpdates 独立连接超时。"""
    from telegram.ext import Application
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(
        connect_timeout=3.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=5.0,
    )
    return (
        Application.builder()
        .token(token)
        .request(request)
        .get_updates_connect_timeout(3.0)
        .get_updates_read_timeout(POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS)
        .get_updates_write_timeout(60.0)
        .get_updates_pool_timeout(5.0)
        # APScheduler 是项目自身调度依赖；Telegram 未使用 PTB JobQueue，禁止自动创建额外调度器。
        .job_queue(None)
        .post_init(_post_init)
        .build()
    )


def _check_bot_ready_for_polling() -> bool:
    """轮询启动前：模块可用且 Token 已配置。"""
    if not PTB_AVAILABLE:
        return False
    token = getattr(settings, "TELEGRAM_TOKEN", None)
    return bool(token and str(token).strip())


def _cleanup_on_polling_conflict(current_pid: int) -> None:
    """409 冲突时释放锁并清理共享状态。"""
    global _bot_started, _active_application
    release_bot_lock()
    _bot_started = False
    _active_application = None
    set_shared_state(
        {
            "bot_initialized": True,
            "bot_running": False,
            "current_pid": None,
            "last_start_time": None,
            "bot_username": None,
        }
    )
    # OS 锁文件保留稳定 inode；释放句柄即可，不得 unlink 活跃锁路径。


def register_handlers(application) -> None:
    """向 Application 注册命令与回调处理器（仅注册一次）。"""
    global _handlers_registered

    if _handlers_registered:
        logger.info("处理器已注册，跳过重复注册")
        return

    from telegram.ext import CallbackQueryHandler, CommandHandler
    from app.core.telegram.command_handlers.id_command import get_chat_id
    from app.core.telegram.command_handlers.start_command import cmd_start
    from app.core.telegram.command_handlers.help_command import cmd_help
    from app.core.telegram.command_handlers.stats_command import cmd_stats
    from app.core.telegram.callback_handlers.menu_callbacks import handle_menu_callbacks
    from app.core.telegram.callback_handlers.stats_callbacks import handle_stats_callbacks
    from app.core.telegram.callback_handlers.postback_approval import handle_postback_approval

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("id", get_chat_id))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(
        CallbackQueryHandler(handle_stats_callbacks, pattern=r"^stats_")
    )
    application.add_handler(
        CallbackQueryHandler(handle_menu_callbacks, pattern=r"^(View|clock)$")
    )
    application.add_handler(
        CallbackQueryHandler(
            handle_postback_approval,
            pattern=r"^postback_(approve|reject)_",
        )
    )

    _handlers_registered = True
    logger.info("消息处理器和回调处理器已成功注册（python-telegram-bot）")


async def _post_init(application) -> None:
    """Application 启动后：删 webhook、设置命令菜单。"""
    from telegram import BotCommand

    await application.bot.delete_webhook(drop_pending_updates=True)
    commands = [
        BotCommand("start", "启动 Bot"),
        BotCommand("help", "显示帮助信息"),
        BotCommand("stats", "广告数据统计（昨天/本周/上周/本月）"),
        BotCommand("id", "查询聊天 ID（群组中需使用 /id@botname）"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Telegram Bot 命令设置成功")


async def _on_error(update, context) -> None:
    """Application 全局错误处理：冲突停轮询，临时网络仅 warning。"""
    error = context.error
    if error is None:
        return
    msg = str(error)
    if is_telegram_conflict_error(msg):
        logger.error("检测到 Telegram 轮询冲突（409），请求 run_polling 优雅退出；error_type=%s", type(error).__name__)
        try:
            # 此错误处理器运行在 Application 事件循环内；stop_running 会让 run_polling
            # 按官方顺序停止 Updater、Application 并执行 shutdown。
            context.application.stop_running()
        except Exception as stop_err:
            logger.warning("409 冲突时停止轮询失败；error_type=%s", type(stop_err).__name__)
        return
    if is_transient_telegram_network_error(error):
        logger.warning("Telegram 轮询临时网络错误，将自动重试；error_type=%s", type(error).__name__)
        return
    logger.error("Telegram Application 未处理错误；error_type=%s", type(error).__name__)


def start_polling():
    """
    启动 Telegram Bot 轮询（仅在获取到锁的进程中启动）

    Returns:
        bool: 是否成功启动并正常结束（冲突返回 False）
    """
    global _bot_started, _active_application, _handlers_registered, _polling_loop

    current_pid = os.getpid()

    if _bot_started:
        logger.info(f"[PID:{current_pid}] Telegram Bot 已经启动，跳过重复启动...")
        return False

    if is_bot_running():
        logger.info(f"[PID:{current_pid}] Telegram Bot 已在其他进程中运行，跳过启动...")
        return False

    logger.info(f"[PID:{current_pid}] 开始启动 Telegram Bot...")

    telegram_enabled = getattr(settings, "TELEGRAM_ENABLE", True)
    if not telegram_enabled:
        logger.info(
            f"[PID:{current_pid}] Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false），跳过启动"
        )
        return False

    if not PTB_AVAILABLE:
        logger.error(
            f"[PID:{current_pid}] python-telegram-bot 未安装，无法启动 Bot"
        )
        return False

    token = getattr(settings, "TELEGRAM_TOKEN", None)
    if not token or not str(token).strip():
        logger.error(f"[PID:{current_pid}] Telegram token 未配置，无法启动")
        return False
    token = str(token).strip()

    delay = random.uniform(0.1, 2.0)
    logger.info(f"[PID:{current_pid}] 等待 {delay:.2f} 秒后尝试获取锁，避免竞争...")
    time.sleep(delay)

    logger.info(f"[PID:{current_pid}] 尝试获取 Telegram Bot 启动锁...")
    lock_acquired = acquire_bot_lock()
    if not lock_acquired:
        logger.info(
            f"[PID:{current_pid}] 其他进程已启动 Telegram Bot，或无法获取锁，跳过启动..."
        )
        return False

    if is_bot_running():
        logger.info(f"[PID:{current_pid}] Telegram Bot 已在其他进程中运行，跳过启动...")
        release_bot_lock()
        return False

    _bot_started = True
    logger.info(f"[PID:{current_pid}] 成功获取锁，标记 Bot 为已启动状态")

    set_shared_state(
        {
            "bot_initialized": True,
            "bot_running": True,
            "current_pid": current_pid,
            "last_start_time": time.time(),
            "bot_username": None,
        }
    )

    from app.core.telegram.bot_state import set_bot_state
    from app.core.telegram.ptb_runtime import get_send_bot, run_on_send_loop

    try:
        send_bot = get_send_bot(token, connect_timeout=3.0, read_timeout=30.0)
        me = run_on_send_loop(send_bot.get_me(), timeout=15.0)
        logger.info(f"[PID:{current_pid}] 验证成功，Bot 可以正常运行：@{me.username}")
        current_state = get_shared_state()
        current_state["bot_username"] = me.username
        set_shared_state(current_state)

        try:
            from app.core.telegram.message_sender import send_telegram_message
            from app.core.constants import TELEGRAM_BOT_START_DELAY
            from app.core.telegram.service_notify import get_service_display_name

            time.sleep(TELEGRAM_BOT_START_DELAY)
            send_telegram_message(
                f"✅ Telegram 机器人轮询已启动（{get_service_display_name()}）"
            )
            logger.info(f"[PID:{current_pid}] 已发送 Telegram 机器人启动消息")
        except Exception as msg_err:
            logger.warning(f"[PID:{current_pid}] 发送启动消息失败；error_type={type(msg_err).__name__}")
    except Exception as e:
        if is_telegram_conflict_error(str(e)):
            logger.error(f"[PID:{current_pid}] 验证失败：检测到其他 Bot 实例正在运行")
            _cleanup_on_polling_conflict(current_pid)
            return False
        logger.warning(f"[PID:{current_pid}] 验证时发生错误，但继续启动；error_type={type(e).__name__}")

    application = _build_polling_application(token)
    _handlers_registered = False
    register_handlers(application)
    application.add_error_handler(_on_error)
    set_bot_state(application.bot, True, True, new_application=application)
    _active_application = application

    logger.info("开始 Telegram Bot 长轮询（python-telegram-bot Application）...")
    try:
        # 轮询跑在 TelegramBot 守护线程，不能注册 POSIX 信号（仅主线程可 add_signal_handler）。
        # 生产 uvicorn/gunicorn + uvloop 下会直接 ValueError，导致轮询秒退、命令无响应。
        # 同时为本线程绑定独立事件循环，避免误用主线程 uvloop。
        thread_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(thread_loop)
        _polling_loop = thread_loop
        application.run_polling(
            timeout=POLLING_LONG_POLL_TIMEOUT_SECONDS,
            bootstrap_retries=POLLING_BOOTSTRAP_RETRIES,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
            close_loop=True,
            stop_signals=None,
        )
    except Exception as e:
        if is_telegram_conflict_error(str(e)):
            logger.error(f"[PID:{current_pid}] 轮询过程中检测到其他 Bot 实例；error_type={type(e).__name__}")
            _cleanup_on_polling_conflict(current_pid)
            return False
        if is_transient_telegram_network_error(e):
            logger.warning(f"轮询意外退出，临时网络错误；error_type={type(e).__name__}")
        else:
            logger.error(f"轮询意外退出；error_type={type(e).__name__}")
    finally:
        _polling_loop = None
        try:
            release_bot_lock()
            logger.info("Telegram Bot 已停止并释放锁")
        except Exception as e:
            logger.warning(f"释放锁时发生错误；error_type={type(e).__name__}")
        _bot_started = False
        _active_application = None
        set_bot_state(None, True, True, new_application=None)
        set_shared_state(
            {
                "bot_initialized": True,
                "bot_running": False,
                "current_pid": None,
                "last_start_time": None,
                "bot_username": None,
            }
        )

    return True


def start_bot_thread():
    """
    在独立线程中启动 Bot 轮询

    Returns:
        bool: 线程是否成功启动（不代表一定获取到锁）
    """
    import threading

    if not _check_bot_ready_for_polling():
        logger.error("python-telegram-bot 不可用或 Token 未配置，无法启动轮询线程")
        return False

    for thread in threading.enumerate():
        if thread.name == "TelegramBot":
            logger.info("Telegram Bot 轮询线程已经在运行，跳过重复启动...")
            return False

    def run_polling():
        logger.info("Telegram Bot 轮询线程开始运行")
        try:
            start_polling()
        except Exception as e:
            logger.error(f"Telegram Bot 轮询线程出错；error_type={type(e).__name__}")
        logger.info("Telegram Bot 轮询线程已结束")

    thread = threading.Thread(target=run_polling, daemon=True, name="TelegramBot")
    thread.start()
    logger.info("Telegram Bot 轮询线程已启动")
    return True


def stop_polling_application(timeout: float = 10.0) -> bool:
    """
    从管理线程请求 PTB run_polling 在其所属事件循环中优雅停止。

    timeout 参数保留兼容旧调用方；停止完成由 restart_bot_thread 的 join 确认。
    """
    app = _active_application
    if app is None:
        from app.core.telegram import bot_state
        app = bot_state.application
    loop = _polling_loop

    if app is None or loop is None or not loop.is_running():
        return False

    try:
        # stop_running 必须在 run_polling 所属事件循环中调用，不能从管理线程直接调用。
        loop.call_soon_threadsafe(app.stop_running)
        logger.info("已向 TelegramBot 事件循环发送优雅停止请求")
        return True
    except Exception as exc:
        logger.warning("请求停止 Telegram 轮询失败；error_type=%s", type(exc).__name__)
        return False


def restart_bot_thread(
    *,
    stop_timeout: float = 10.0,
    join_timeout: float = 15.0,
) -> dict:
    """
    先向 PTB run_polling 请求优雅退出，再等待旧线程真正结束后才启动新实例。

    如果旧线程无法在 join_timeout 内退出，则 fail closed：不释放其锁、不清状态、
    不启动第二个轮询线程。
    """
    import threading
    import time

    global _bot_started, _handlers_registered

    stopped = stop_polling_application(timeout=stop_timeout)

    bot_threads = [
        thread for thread in threading.enumerate() if thread.name == "TelegramBot"
    ]
    for bot_thread in bot_threads:
        if bot_thread.is_alive():
            bot_thread.join(timeout=join_timeout)
    thread_joined = all(not thread.is_alive() for thread in bot_threads)

    if not thread_joined:
        logger.error(
            "TelegramBot 旧线程在 %.0f 秒内未退出；为避免双 polling，拒绝释放锁和启动新线程",
            join_timeout,
        )
        return {
            "stopped": bool(stopped),
            "thread_joined": False,
            "started": False,
            "restarted": False,
        }

    # 旧线程已退出，其 finally 已正常释放锁并清理状态；此处只兜底清理本进程句柄。
    try:
        release_bot_lock()
    except Exception as exc:
        logger.warning("旧线程退出后的锁清理失败；error_type=%s", type(exc).__name__)

    set_shared_state(
        {
            "bot_initialized": True,
            "bot_running": False,
            "current_pid": None,
            "last_start_time": None,
            "bot_username": None,
        }
    )

    _bot_started = False
    _handlers_registered = False
    time.sleep(0.5)

    started = start_bot_thread()
    return {
        "stopped": bool(stopped),
        "thread_joined": True,
        "started": bool(started),
        "restarted": bool(started),
    }
