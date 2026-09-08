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
# 启动 loop 用短锁；Bot 创建用独立锁，禁止在持锁时 future.result()（会死锁）
_loop_start_lock = threading.Lock()
_send_bot_lock = threading.Lock()
_SEND_LOOP_READY = threading.Event()


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
    """
    loop = ensure_send_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


async def _create_send_bot(token: str, *, connect_timeout: float, read_timeout: float):
    from telegram import Bot
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=read_timeout,
    )
    bot = Bot(token=token, request=request)
    await bot.initialize()
    return bot


def get_send_bot(
    token: str,
    *,
    connect_timeout: float = 3.0,
    read_timeout: float = 30.0,
):
    """
    获取（或重建）发送专用 Bot 实例，绑定在发送 loop 上。

    注意：不得在持有锁时调用 run_on_send_loop（会与 ensure_send_loop 死锁）。
    """
    global _send_bot, _send_bot_token
    if not token or not str(token).strip():
        raise ValueError("Telegram token 为空")
    token = token.strip()

    with _send_bot_lock:
        if _send_bot is not None and _send_bot_token == token:
            return _send_bot
        old_bot = _send_bot

    async def _build():
        if old_bot is not None:
            try:
                await old_bot.shutdown()
            except Exception as exc:
                logger.debug("关闭旧发送 Bot 失败（可忽略）: %s", exc)
        return await _create_send_bot(
            token,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )

    new_bot = run_on_send_loop(
        _build(),
        timeout=max(10.0, connect_timeout + read_timeout),
    )

    with _send_bot_lock:
        if _send_bot is not None and _send_bot_token == token:
            # 其它线程已抢先建好，丢弃本次实例
            async def _shutdown_dup():
                try:
                    await new_bot.shutdown()
                except Exception:
                    pass

            try:
                run_on_send_loop(_shutdown_dup(), timeout=5.0)
            except Exception:
                pass
            return _send_bot
        _send_bot = new_bot
        _send_bot_token = token
        return _send_bot


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
