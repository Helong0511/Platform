"""
程序运行错误 Telegram 通知。

统一从 ERROR 日志、全局异常处理器等入口推送管理员告警；含防抖与噪音过滤。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
import traceback
from typing import Any, Optional

from app.core.config import settings
from app.core.telegram.service_notify import get_service_display_name

logger = logging.getLogger(__name__)

_DEFAULT_DEBOUNCE_SECONDS = 300
_mem_alert_ts: dict[str, float] = {}
_mem_lock = threading.Lock()

# 日志 Handler 专用：这些 logger 已走显式 notify，避免重复推送
_LOG_HANDLER_EXCLUDED_LOGGER_PREFIXES = (
    "app.bootstrap.exception_handlers",
)

# 全局噪音过滤（递归/第三方库等，所有入口均生效）
_EXCLUDED_LOGGER_PREFIXES = (
    "app.core.telegram",
    "telebot",
    "urllib3",
    "httpx",
    "httpcore",
)

# 正常断连/临时网络问题，不推送
_NOISE_SUBSTRINGS = (
    "EndOfStream",
    "WouldBlock",
    "客户端已断开连接",
    "连接已断开",
    "Telegram 轮询临时网络错误",
    "Telegram 轮询冲突",
    "发送 Telegram 通知整体超时",
    "Bot 不可用，无法发送消息",
    # 上游广告 API 瞬时故障（已重试耗尽后的软容错；非本程序逻辑错误）
    "All connection attempts failed",
    "UpstreamTransientError",
    "软跳过: 上游暂时不可达",
    "请求超时: 超过",
    " 请求失败: ",
    "HTTP错误: 状态码=429",
    "HTTP错误: 状态码=500",
    "HTTP错误: 状态码=502",
    "HTTP错误: 状态码=503",
    "HTTP错误: 状态码=504",
)


def _is_enabled() -> bool:
    if not getattr(settings, "TELEGRAM_ENABLE", True):
        return False
    if not getattr(settings, "TELEGRAM_RUNTIME_ERROR_NOTIFY", True):
        return False
    admin = getattr(settings, "TELEGRAM_ADMIN", None)
    return bool(admin and str(admin).strip())


def _error_fingerprint(error_type: str, message: str, location: str = "") -> str:
    raw = f"{error_type}|{location}|{message[:300]}"
    return hashlib.md5(raw.encode("utf-8", errors="replace")).hexdigest()


def _should_send_alert(fingerprint: str) -> bool:
    debounce = int(
        getattr(settings, "TELEGRAM_RUNTIME_ERROR_DEBOUNCE_SECONDS", _DEFAULT_DEBOUNCE_SECONDS)
    )
    now = time.time()
    with _mem_lock:
        last = _mem_alert_ts.get(fingerprint, 0.0)
        if now - last < debounce:
            return False
        _mem_alert_ts[fingerprint] = now
    return True


def is_noise_error(
        error_type: str,
        message: str,
        *,
        logger_name: str = "",
) -> bool:
    """判断是否为无需推送的噪音错误（全局过滤）。"""
    for prefix in _EXCLUDED_LOGGER_PREFIXES:
        if logger_name.startswith(prefix):
            return True
    text = f"{error_type} {message}"
    return any(token in text for token in _NOISE_SUBSTRINGS)


def _is_log_handler_excluded(logger_name: str) -> bool:
    """日志 Handler 专用：已由显式 notify 处理的路径不再重复推送。"""
    return any(logger_name.startswith(prefix) for prefix in _LOG_HANDLER_EXCLUDED_LOGGER_PREFIXES)


def build_runtime_error_message(
        *,
        error_type: str,
        error_message: str,
        location: Optional[dict[str, str]] = None,
        context: Optional[dict[str, Any]] = None,
        stack_trace: Optional[str] = None,
) -> str:
    """拼装运行时错误 Telegram 正文。"""
    service = get_service_display_name()
    host = os.getenv("HOSTNAME") or os.getenv("COMPUTERNAME") or "-"
    pid = os.getpid()

    lines = [
        "🚨 程序运行错误",
        "",
        f"服务：{service}",
        f"主机：{host}  PID：{pid}",
        f"类型：{error_type}",
        f"错误：{error_message[:500]}",
    ]

    if location:
        loc_parts = []
        for key in ("module", "function", "line", "file"):
            if location.get(key):
                loc_parts.append(f"{key}={location[key]}")
        if loc_parts:
            lines.append(f"位置：{', '.join(loc_parts)}")

    if context:
        lines.append("")
        lines.append("上下文：")
        for key, value in list(context.items())[:8]:
            if value is None:
                continue
            lines.append(f"  {key}: {str(value)[:200]}")

    if stack_trace:
        lines.append("")
        lines.append("堆栈（截断）：")
        lines.append(stack_trace[:1200])

    lines.append("")
    lines.append(f"⏰ {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def _send_sync(message: str) -> None:
    """在独立线程中同步发送，避免阻塞日志/请求线程。"""
    try:
        from app.core.telegram.message_sender import send_telegram_message

        send_telegram_message(message)
    except Exception as exc:
        # 仅写本地日志，禁止再次触发 Telegram 通知
        logging.getLogger("app.core.telegram.runtime_error_notify").warning(
            "运行时错误 Telegram 通知发送失败: %s", exc
        )


def notify_runtime_error_sync(
        *,
        error_type: str,
        error_message: str,
        location: Optional[dict[str, str]] = None,
        context: Optional[dict[str, Any]] = None,
        stack_trace: Optional[str] = None,
        logger_name: str = "",
) -> bool:
    """
    同步调度运行时错误 Telegram 通知（防抖 + 噪音过滤）。

    Returns:
        是否已提交发送
    """
    if not _is_enabled():
        return False
    if is_noise_error(error_type, error_message, logger_name=logger_name):
        return False

    loc_key = ""
    if location:
        loc_key = f"{location.get('module', '')}:{location.get('function', '')}:{location.get('line', '')}"
    fingerprint = _error_fingerprint(error_type, error_message, loc_key)
    if not _should_send_alert(fingerprint):
        return False

    message = build_runtime_error_message(
        error_type=error_type,
        error_message=error_message,
        location=location,
        context=context,
        stack_trace=stack_trace,
    )
    threading.Thread(target=_send_sync, args=(message,), daemon=True).start()
    return True


async def notify_runtime_error_async(
        *,
        error_type: str,
        error_message: str,
        location: Optional[dict[str, str]] = None,
        context: Optional[dict[str, Any]] = None,
        stack_trace: Optional[str] = None,
        logger_name: str = "",
) -> bool:
    """异步上下文中调度运行时错误通知。"""
    return await asyncio.to_thread(
        notify_runtime_error_sync,
        error_type=error_type,
        error_message=error_message,
        location=location,
        context=context,
        stack_trace=stack_trace,
        logger_name=logger_name,
    )


def notify_from_log_record(record: logging.LogRecord) -> bool:
    """从 logging.LogRecord 提取信息并推送通知。"""
    if _is_log_handler_excluded(record.name):
        return False

    error_type = record.levelname
    error_message = record.getMessage()

    stack_trace = None
    if record.exc_info:
        error_type = record.exc_info[0].__name__ if record.exc_info[0] else error_type
        stack_trace = "".join(traceback.format_exception(*record.exc_info))
        if not error_message and record.exc_info[1]:
            error_message = str(record.exc_info[1])

    location = {
        "module": record.name,
        "function": record.funcName,
        "line": str(record.lineno),
        "file": record.pathname,
    }
    return notify_runtime_error_sync(
        error_type=error_type,
        error_message=error_message,
        location=location,
        stack_trace=stack_trace,
        logger_name=record.name,
    )
