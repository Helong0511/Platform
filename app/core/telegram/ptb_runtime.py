"""
python-telegram-bot 运行时辅助。

提供：
- 模块可用性检测
- 独立发送用事件循环（与 Application 轮询线程隔离，避免跨 loop 复用 Bot）
- 同步代码中安全执行 PTB 协程
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import TimeoutError as FutureTimeoutError
import threading
from typing import Any, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

PTB_AVAILABLE = False
try:
    from telegram import Bot  # noqa: F401
    from telegram.request import HTTPXRequest  # noqa: F401

    PTB_AVAILABLE = True
except ImportError as import_err:
    logger.warning(
        "python-telegram-bot 未安装，Telegram Bot 功能将不可用。"
        "请运行：pip install 'python-telegram-bot==22.8'。详情：%s",
        import_err,
    )

_send_loop: Optional[asyncio.AbstractEventLoop] = None
_send_thread: Optional[threading.Thread] = None
_send_bot: Any = None
_send_bot_token: Optional[str] = None
# 事件循环启动锁只保护线程创建；Bot 缓存锁只保护引用读写。
# Bot 重建锁串行化“旧实例关闭 -> 新实例创建 -> 缓存发布”整个生命周期；
# 不持有缓存锁等待 future.result()，避免把慢网络操作放进短临界区。
_loop_start_lock = threading.Lock()
_send_bot_lock = threading.Lock()
_send_bot_rebuild_lock = threading.Lock()
_SEND_LOOP_READY = threading.Event()

# 发送 Bot 是进程级单例，所有调用方必须共享一致的 HTTPX 超时配置。
SEND_BOT_CONNECT_TIMEOUT_SECONDS = 3.0
SEND_BOT_READ_TIMEOUT_SECONDS = 30.0


def _send_loop_worker() -> None:
    """发送专用事件循环线程入口。"""
    global _send_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _send_loop = loop
    _SEND_LOOP_READY.set()
    loop.run_forever()


def ensure_send_loop() -> asyncio.AbstractEventLoop:
    """确保发送专用事件循环已启动，并返回该 loop。"""
    global _send_thread
    if _send_loop is not None and _send_loop.is_running():
        return _send_loop

    with _loop_start_lock:
        if _send_loop is not None and _send_loop.is_running():
            return _send_loop
        _SEND_LOOP_READY.clear()
        _send_thread = threading.Thread(
            target=_send_loop_worker,
            name="TelegramSendLoop",
            daemon=True,
        )
        _send_thread.start()

    if not _SEND_LOOP_READY.wait(timeout=5.0):
        raise RuntimeError("Telegram 发送事件循环启动超时")
    assert _send_loop is not None
    return _send_loop


def run_on_send_loop(coro, *, timeout: Optional[float] = None):
    """
    在发送专用 loop 上执行协程并同步等待结果。

    可从任意线程调用（含已有 running loop 的 async 上下文）。
    PTB Bot API coroutine 必须在 send loop 执行；调用方不得在自己的 loop 直接 await。
    不得直接在 ASGI/async handler 中调用，应使用 run_on_send_loop_async。
    """
    loop = ensure_send_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        # 超时后必须通知 loop 取消底层协程，避免请求在调用方已重试后仍继续发送。
        future.cancel()
        raise


async def run_on_send_loop_async(coro, *, timeout: Optional[float] = None):
    """在 async handler 中非阻塞地等待发送 loop，避免占用当前事件循环。"""
    return await asyncio.to_thread(run_on_send_loop, coro, timeout=timeout)


async def _create_send_bot(token: str):
    from telegram import Bot
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(
        connect_timeout=SEND_BOT_CONNECT_TIMEOUT_SECONDS,
        read_timeout=SEND_BOT_READ_TIMEOUT_SECONDS,
        write_timeout=SEND_BOT_READ_TIMEOUT_SECONDS,
    )
    bot = Bot(token=token, request=request)
    await bot.initialize()
    return bot


def get_send_bot(token: str):
    """
    获取（或重建）发送专用 Bot 实例，绑定在发送 loop 上。

    重建锁串行化旧 Bot shutdown、新 Bot 创建和缓存发布，避免不同 Token 的
    并发调用互相关闭/覆盖实例。缓存锁只用于短暂读写，不跨越网络等待。
    """
    global _send_bot, _send_bot_token
    if not token or not str(token).strip():
        raise ValueError("Telegram token 为空")
    token = token.strip()

    with _send_bot_rebuild_lock:
        with _send_bot_lock:
            if _send_bot is not None and _send_bot_token == token:
                return _send_bot
            old_bot = _send_bot
            # 先解除旧缓存引用；即使新实例构建失败，也不会把已 shutdown 的 Bot
            # 继续作为可用实例返回给后续调用。
            _send_bot = None
            _send_bot_token = None

        async def _build():
            if old_bot is not None:
                try:
                    await old_bot.shutdown()
                except Exception as exc:
                    logger.warning(
                        "关闭旧发送 Bot 失败；error_type=%s",
                        type(exc).__name__,
                    )
            return await _create_send_bot(token)

        new_bot = run_on_send_loop(
            _build(),
            timeout=max(
                10.0,
                SEND_BOT_CONNECT_TIMEOUT_SECONDS
                + SEND_BOT_READ_TIMEOUT_SECONDS
                + 7.0,
            ),
        )

        with _send_bot_lock:
            _send_bot = new_bot
            _send_bot_token = token
        return new_bot


def build_inline_keyboard(buttons: list[list[dict[str, Any]]]):
    """将 [{text, callback_data}] 二维列表转为 PTB InlineKeyboardMarkup。"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    for row in buttons:
        rows.append(
            [
                InlineKeyboardButton(
                    text=btn.get("text", ""),
                    callback_data=btn.get("callback_data", ""),
                )
                for btn in row
            ]
        )
    return InlineKeyboardMarkup(rows)


def count_application_handlers(application) -> int:
    """统计 Application 已注册的 handler 数量。"""
    if application is None:
        return 0
    total = 0
    handlers = getattr(application, "handlers", None) or {}
    for _group, group_handlers in handlers.items():
        total += len(group_handlers or [])
    return total
