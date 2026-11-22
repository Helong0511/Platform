"""
Telegram Bot 轮询管理模块

使用 python-telegram-bot Application.run_polling 做长轮询（守护线程）。
"""
import asyncio
import os
import time
import logging
import random
import threading
from typing import Optional

logger = logging.getLogger(__name__)

from app.core.telegram.file_lock import acquire_bot_lock, release_bot_lock, is_lock_held
from app.core.telegram.shared_state import (
    get_shared_state,
    set_shared_state,
    is_bot_running,
)
from app.core.config import settings
from app.core.telegram.polling_exception_handler import (
    is_permanent_telegram_auth_error,
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
POLLING_LONG_POLL_TIMEOUT_SECONDS = 10
POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS = 65.0
POLLING_BOOTSTRAP_RETRIES = 3



# 运行期 supervisor：PTB bootstrap 重试耗尽/异常退出后，由唯一 TelegramBot 线程有限恢复。
POLLING_SUPERVISOR_MAX_RESTARTS = 5
POLLING_SUPERVISOR_BASE_DELAY_SECONDS = 2.0
POLLING_SUPERVISOR_MAX_DELAY_SECONDS = 60.0
POLLING_SUPERVISOR_JITTER_SECONDS = 1.0
POLLING_HEALTH_STALE_AFTER_SECONDS = 180.0
POLLING_HEALTH_CHECK_INTERVAL_SECONDS = 30.0

_supervisor_stop_event = threading.Event()
_supervisor_running = False
_last_polling_exit_reason = "not_started"
_last_polling_error_at: Optional[float] = None
_last_get_updates_success_at: Optional[float] = None
_last_update_received_at: Optional[float] = None
_supervisor_restart_count = 0


def get_polling_health_status() -> dict:
    """返回轮询线程与 getUpdates 成功心跳；线程存活本身不等于健康。"""
    now = time.time()
    thread_alive = any(
        thread.name == "TelegramBot" and thread.is_alive()
        for thread in threading.enumerate()
    )
    shared_state = get_shared_state()
    shared_pid = shared_state.get("current_pid")
    remote_owner_alive = bool(
        shared_state.get("bot_running")
        and shared_pid is not None
        and shared_pid != os.getpid()
        and is_bot_running()
    )
    is_owner = is_lock_held()
    success_at = _last_get_updates_success_at
    success_age = None if success_at is None else max(0.0, now - success_at)
    healthy = bool(
        is_owner
        and thread_alive
        and _supervisor_running
        and success_age is not None
        and success_age <= POLLING_HEALTH_STALE_AFTER_SECONDS
    )
    return {
        "is_owner": is_owner,
        "remote_owner_alive": remote_owner_alive,
        "thread_alive": thread_alive,
        "supervisor_running": _supervisor_running,
        "healthy": healthy,
        "last_exit_reason": _last_polling_exit_reason,
        "last_error_at": _last_polling_error_at,
        "last_get_updates_success_at": success_at,
        "last_get_updates_success_age_seconds": success_age,
        "last_update_received_at": _last_update_received_at,
        "restart_count": _supervisor_restart_count,
    }


async def _record_update_received(_update, _context) -> None:
    """记录最近一次成功收到并交给 PTB 处理的 Update 时间。"""
    global _last_update_received_at
    _last_update_received_at = time.time()


def _create_health_tracked_bot_class(base_bot_class):
    """通过 Bot 子类记录 getUpdates 成功返回；PTB Bot 使用 __slots__，不能实例 monkeypatch。"""

    class HealthTrackedBot(base_bot_class):
        async def get_updates(self, *args, **kwargs):
            global _last_get_updates_success_at
            result = await super().get_updates(*args, **kwargs)
            _last_get_updates_success_at = time.time()
            return result

    return HealthTrackedBot


def _notify_supervisor_failure(reason: str) -> None:
    """通过现有去重通知通道发送不含 Token/异常正文的 supervisor 告警。"""
    try:
        from app.core.telegram.runtime_error_notify import notify_runtime_error_sync

        notify_runtime_error_sync(
            error_type="TelegramPollingSupervisor",
            error_message=f"Telegram polling supervisor stopped or circuit-opened: {reason}",
            location={
                "module": "app.core.telegram.polling_manager",
                "function": "start_bot_thread",
            },
        )
    except Exception as exc:
        logger.warning(
            "Telegram polling supervisor 告警调度失败；error_type=%s",
            type(exc).__name__,
        )


def _polling_health_watchdog() -> None:
    """运行期网络重试若长期没有成功 getUpdates，发一次告警；恢复后允许再次告警。"""
    alert_sent = False
    while not _supervisor_stop_event.wait(POLLING_HEALTH_CHECK_INTERVAL_SECONDS):
        success_at = _last_get_updates_success_at
        if success_at is None:
            continue
        stale = time.time() - success_at > POLLING_HEALTH_STALE_AFTER_SECONDS
        if stale and not alert_sent:
            _notify_supervisor_failure("getUpdates heartbeat stale")
            alert_sent = True
        elif not stale:
            alert_sent = False


def _build_polling_application(token: str):
    """构建带成功心跳的 PTB Application，并显式配置 getUpdates 独立连接超时。"""
    from telegram.ext import Application, ExtBot
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(
        connect_timeout=3.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=5.0,
    )
    get_updates_request = HTTPXRequest(
        connect_timeout=3.0,
        read_timeout=POLLING_GET_UPDATES_READ_TIMEOUT_SECONDS,
        write_timeout=60.0,
        pool_timeout=5.0,
    )
    tracked_bot_class = _create_health_tracked_bot_class(ExtBot)
    bot = tracked_bot_class(
        token=token,
        request=request,
        get_updates_request=get_updates_request,
    )
    return (
        Application.builder()
        .bot(bot)
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
    """409 冲突时清理共享状态；OS 锁由 start_polling 外层 finally 统一释放。"""
    global _bot_started, _active_application, _last_polling_exit_reason
    _last_polling_exit_reason = "conflict"
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

    from telegram import Update
    from telegram.ext import CallbackQueryHandler, CommandHandler, TypeHandler
    from app.core.telegram.command_handlers.id_command import get_chat_id
    from app.core.telegram.command_handlers.start_command import cmd_start
    from app.core.telegram.command_handlers.help_command import cmd_help
    from app.core.telegram.command_handlers.stats_command import cmd_stats
    from app.core.telegram.callback_handlers.menu_callbacks import handle_menu_callbacks
    from app.core.telegram.callback_handlers.stats_callbacks import handle_stats_callbacks
    from app.core.telegram.callback_handlers.postback_approval import handle_postback_approval

    # 负 group 仅记录 Update 心跳；不抢占默认 group 中的业务 Handler。
    application.add_handler(TypeHandler(Update, _record_update_received), group=-1)
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
    global _last_polling_exit_reason, _last_polling_error_at
    error = context.error
    if error is None:
        return
    _last_polling_error_at = time.time()
    msg = str(error)
    if is_telegram_conflict_error(msg):
        _last_polling_exit_reason = "conflict"
        logger.error("检测到 Telegram 轮询冲突（409），请求 run_polling 优雅退出；error_type=%s", type(error).__name__)
        try:
            # 此错误处理器运行在 Application 事件循环内；stop_running 会让 run_polling
            # 按官方顺序停止 Updater、Application 并执行 shutdown。
            context.application.stop_running()
        except Exception as stop_err:
            logger.warning("409 冲突时停止轮询失败；error_type=%s", type(stop_err).__name__)
        return
    if is_permanent_telegram_auth_error(error):
        _last_polling_exit_reason = "permanent_auth_error"
        logger.error("Telegram 轮询认证失败，停止自动重试；error_type=%s", type(error).__name__)
        try:
            context.application.stop_running()
        except Exception as stop_err:
            logger.warning("认证失败时停止轮询失败；error_type=%s", type(stop_err).__name__)
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
    global _last_polling_exit_reason, _last_get_updates_success_at, _last_polling_error_at

    if threading.current_thread().name != "TelegramBot":
        _supervisor_stop_event.clear()
    _last_polling_exit_reason = "starting"
    _last_get_updates_success_at = None
    current_pid = os.getpid()

    if _bot_started:
        _last_polling_exit_reason = "already_running"
        logger.info(f"[PID:{current_pid}] Telegram Bot 已经启动，跳过重复启动...")
        return False

    if is_bot_running():
        _last_polling_exit_reason = "already_running"
        logger.info(f"[PID:{current_pid}] Telegram Bot 已在其他进程中运行，跳过启动...")
        return False

    logger.info(f"[PID:{current_pid}] 开始启动 Telegram Bot...")

    telegram_enabled = getattr(settings, "TELEGRAM_ENABLE", True)
    if not telegram_enabled:
        _last_polling_exit_reason = "disabled"
        logger.info(
            f"[PID:{current_pid}] Telegram Bot 功能已禁用（TELEGRAM_ENABLE=false），跳过启动"
        )
        return False

    if not PTB_AVAILABLE:
        _last_polling_exit_reason = "dependency_unavailable"
        logger.error(
            f"[PID:{current_pid}] python-telegram-bot 未安装，无法启动 Bot"
        )
        return False

    token = getattr(settings, "TELEGRAM_TOKEN", None)
    if not token or not str(token).strip():
        _last_polling_exit_reason = "configuration_error"
        logger.error(f"[PID:{current_pid}] Telegram token 未配置，无法启动")
        return False
    token = str(token).strip()

    delay = random.uniform(0.1, 2.0)
    logger.info(f"[PID:{current_pid}] 等待 {delay:.2f} 秒后尝试获取锁，避免竞争...")
    time.sleep(delay)

    logger.info(f"[PID:{current_pid}] 尝试获取 Telegram Bot 启动锁...")
    lock_acquired = acquire_bot_lock()
    if not lock_acquired:
        _last_polling_exit_reason = "lock_not_acquired"
        logger.info(
            f"[PID:{current_pid}] 其他进程已启动 Telegram Bot，或无法获取锁，跳过启动..."
        )
        return False


    # 成功获取 OS 锁后，所有初始化和运行步骤必须处于同一个 finally 生命周期内。
    entered_runtime = False
    try:
        if is_bot_running():
            _last_polling_exit_reason = "already_running"
            logger.info(
                f"[PID:{current_pid}] Telegram Bot 已在其他进程中运行，跳过启动..."
            )
            return False
        entered_runtime = True
        try:
            result = _start_polling_with_lock(current_pid, token)
            if _last_polling_exit_reason == "starting":
                _last_polling_exit_reason = (
                    "stopped" if _supervisor_stop_event.is_set() else "unexpected_return"
                )
            return result
        except Exception as exc:
            _last_polling_error_at = time.time()
            if is_telegram_conflict_error(str(exc)):
                _last_polling_exit_reason = "conflict"
            elif is_permanent_telegram_auth_error(exc):
                _last_polling_exit_reason = "permanent_auth_error"
            elif is_transient_telegram_network_error(exc):
                _last_polling_exit_reason = "transient_network_error"
            else:
                _last_polling_exit_reason = "unexpected_exception"
            raise
    finally:
        # 无论导入、Bot 探测、Application 构建、Handler 注册还是 run_polling 抛错，
        # 都必须释放当前进程刚取得的 OS 锁。状态清理只在本次启动已进入运行阶段时执行。
        try:
            release_bot_lock()
        except Exception as cleanup_error:
            logger.warning(
                "Telegram Bot 启动清理时释放锁失败；error_type=%s",
                type(cleanup_error).__name__,
            )
        if entered_runtime:
            _polling_loop = None
            _bot_started = False
            _active_application = None
            try:
                from app.core.telegram.bot_state import set_bot_state
                set_bot_state(None, True, True, new_application=None)
            except Exception as cleanup_error:
                logger.warning(
                    "Telegram Bot 状态清理失败；error_type=%s",
                    type(cleanup_error).__name__,
                )
            set_shared_state(
                {
                    "bot_initialized": True,
                    "bot_running": False,
                    "current_pid": None,
                    "last_start_time": None,
                    "bot_username": None,
                }
            )


def _start_polling_with_lock(current_pid: int, token: str) -> bool:
    """调用方已持有 OS 锁；执行 Bot 验证、构建、注册和轮询。"""
    global _bot_started, _active_application, _handlers_registered, _polling_loop
    global _last_polling_exit_reason, _last_polling_error_at

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
        send_bot = get_send_bot(token)
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
        _last_polling_error_at = time.time()
        if is_telegram_conflict_error(str(e)):
            _last_polling_exit_reason = "conflict"
            logger.error(f"[PID:{current_pid}] 轮询过程中检测到其他 Bot 实例；error_type={type(e).__name__}")
            _cleanup_on_polling_conflict(current_pid)
            return False
        if is_permanent_telegram_auth_error(e):
            _last_polling_exit_reason = "permanent_auth_error"
            logger.error(f"轮询认证失败，停止自动重试；error_type={type(e).__name__}")
        elif is_transient_telegram_network_error(e):
            _last_polling_exit_reason = "transient_network_error"
            logger.warning(f"轮询意外退出，临时网络错误；error_type={type(e).__name__}")
        else:
            _last_polling_exit_reason = "unexpected_exception"
            logger.error(f"轮询意外退出；error_type={type(e).__name__}")

    return True


def _run_polling_supervisor() -> None:
    """唯一 TelegramBot 线程监督 polling 生命周期，并对可恢复退出做有限退避。"""
    global _supervisor_running, _supervisor_restart_count, _last_polling_exit_reason
    global _last_polling_error_at

    _supervisor_running = True
    _supervisor_restart_count = 0
    watchdog = threading.Thread(
        target=_polling_health_watchdog,
        name="TelegramPollingHealthWatchdog",
        daemon=True,
    )
    watchdog.start()

    try:
        while not _supervisor_stop_event.is_set():
            try:
                start_polling()
            except Exception as exc:
                _last_polling_error_at = time.time()
                if is_telegram_conflict_error(str(exc)):
                    _last_polling_exit_reason = "conflict"
                elif is_permanent_telegram_auth_error(exc):
                    _last_polling_exit_reason = "permanent_auth_error"
                elif is_transient_telegram_network_error(exc):
                    _last_polling_exit_reason = "transient_network_error"
                else:
                    _last_polling_exit_reason = "unexpected_exception"
                logger.error(
                    "Telegram polling supervisor 捕获启动异常；reason=%s error_type=%s",
                    _last_polling_exit_reason,
                    type(exc).__name__,
                )

            reason = _last_polling_exit_reason
            if _supervisor_stop_event.is_set() or reason == "stopped":
                break

            if reason in {"conflict", "permanent_auth_error"}:
                logger.error(
                    "Telegram polling supervisor 进入停止/熔断状态：reason=%s",
                    reason,
                )
                _notify_supervisor_failure(reason)
                break

            if reason in {"disabled", "dependency_unavailable", "configuration_error"}:
                logger.error(
                    "Telegram polling supervisor 配置不可用，停止自动重试：reason=%s",
                    reason,
                )
                _notify_supervisor_failure(reason)
                break

            if reason in {"already_running", "lock_not_acquired"}:
                logger.info(
                    "Telegram polling supervisor 未取得启动所有权，不进行重试：reason=%s",
                    reason,
                )
                break

            if reason not in {
                "transient_network_error",
                "unexpected_return",
                "unexpected_exception",
            }:
                logger.error(
                    "Telegram polling supervisor 遇到未知退出状态，停止自动重试：reason=%s",
                    reason,
                )
                _notify_supervisor_failure("unknown exit state")
                break

            if _supervisor_restart_count >= POLLING_SUPERVISOR_MAX_RESTARTS:
                logger.error(
                    "Telegram polling supervisor 达到最大恢复次数，进入熔断：restarts=%s",
                    _supervisor_restart_count,
                )
                _notify_supervisor_failure("maximum restart attempts reached")
                break

            attempt = _supervisor_restart_count + 1
            delay = min(
                POLLING_SUPERVISOR_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
                POLLING_SUPERVISOR_MAX_DELAY_SECONDS,
            ) + random.uniform(0.0, POLLING_SUPERVISOR_JITTER_SECONDS)
            _supervisor_restart_count = attempt
            logger.warning(
                "Telegram polling 将在退避后重启：attempt=%s/%s delay_seconds=%.2f reason=%s",
                attempt,
                POLLING_SUPERVISOR_MAX_RESTARTS,
                delay,
                reason,
            )
            if _supervisor_stop_event.wait(delay):
                break
    finally:
        _supervisor_stop_event.set()
        _supervisor_running = False
        logger.info(
            "Telegram polling supervisor 已结束：last_reason=%s restarts=%s",
            _last_polling_exit_reason,
            _supervisor_restart_count,
        )


def start_bot_thread():
    """
    在独立线程中启动 Telegram polling supervisor。

    Returns:
        bool: supervisor 线程是否成功启动（不代表已经取得 OS 锁或轮询健康）。
    """
    if not _check_bot_ready_for_polling():
        logger.error("python-telegram-bot 不可用或 Token 未配置，无法启动轮询线程")
        return False

    for thread in threading.enumerate():
        if thread.name == "TelegramBot" and thread.is_alive():
            logger.info("Telegram Bot 轮询线程已经在运行，跳过重复启动...")
            return False

    _supervisor_stop_event.clear()
    thread = threading.Thread(
        target=_run_polling_supervisor,
        daemon=True,
        name="TelegramBot",
    )
    try:
        thread.start()
    except Exception as exc:
        logger.error(
            "Telegram polling supervisor 线程启动失败；error_type=%s",
            type(exc).__name__,
        )
        return False
    logger.info("Telegram Bot polling supervisor 线程已启动")
    return True

def stop_polling_application(timeout: float = 10.0) -> bool:
    """
    从管理线程请求 PTB run_polling 在其所属事件循环中优雅停止。

    timeout 参数保留兼容旧调用方；停止完成由 restart_bot_thread 的 join 确认。
    """
    _supervisor_stop_event.set()
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
