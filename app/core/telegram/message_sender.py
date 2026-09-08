"""
Telegram 消息发送模块

提供消息发送功能，包括普通消息、带按钮消息和管理员通知。

限流说明：
- Telegram 对同一 Chat 约 1 条/秒；Bot 全局也有配额。
- API 多 worker + Scheduler 各自持有进程内间隔时会互相踩踏 → 连环 429。
- 本模块用 Redis（若可用）做跨进程 per-chat / 全局闸门，并在 429 时写入共享退避，
  避免多进程同时 ``sleep(retry_after)`` 后再一起打爆。
"""
import logging
import importlib
import math
import os
import re
import threading
import time
from typing import Optional, List, Dict, Any

from app.core.telegram_utils import truncate_message, MAX_TELEGRAM_MESSAGE_LENGTH, validate_chat_id
from app.core.config import settings

logger = logging.getLogger(__name__)

# 消息发送配置
MAX_RETRIES = 3  # 最大重试次数
BASE_RETRY_DELAY = 2  # 基础重试延迟（秒）
TIMEOUT_SECONDS = 30  # 超时时间（秒），适当增大避免网络波动导致误判
# 同 Chat 约 1 条/秒；多 Chat 批量发送时也按此间隔错开
MIN_SEND_INTERVAL = 1.1
INTER_CHAT_DELAY = 1.1
# 全局（跨 Chat）最小间隔，防止 Bot 级配额被打满（约 20～25 条/秒上限，留余量）
MIN_GLOBAL_SEND_INTERVAL = 0.05
MAX_RATE_LIMIT_WAIT = 120  # 429 限流时最长等待秒数
_REDIS_BACKOFF_GLOBAL = "telegram:send:backoff:__global__"
_REDIS_GATE_GLOBAL = "telegram:send:gate:__global__"
_REDIS_BACKOFF_CHAT = "telegram:send:backoff:{chat_id}"
_REDIS_GATE_CHAT = "telegram:send:gate:{chat_id}"
_SYNC_REDIS_FAIL_BACKOFF = 30.0

_sync_redis_client = None
_sync_redis_lock = threading.Lock()
_sync_redis_failed_until = 0.0


def estimate_telegram_send_timeout_seconds(chat_count: int = 1) -> float:
    """
    估算单次发送的合理外层超时（含多 Chat、重试与退避上限）。

    避免业务侧 ``wait_for(5)`` 过早取消导致孤儿线程继续重试并打出双 ERROR。
    """
    n = max(1, int(chat_count))
    # 每 Chat：API 超时重试 + 429 退避上限 + 闸门间隔；Chat 间间隔；再留缓冲
    per_chat = (
        TIMEOUT_SECONDS * MAX_RETRIES
        + MAX_RATE_LIMIT_WAIT * (MAX_RETRIES - 1)
        + MIN_SEND_INTERVAL * 2
    )
    return float(per_chat * n + INTER_CHAT_DELAY * n + 30.0)


def _admin_chat_count() -> int:
    admin = getattr(settings, "TELEGRAM_ADMIN", None) or ""
    return max(1, len([c for c in str(admin).split(",") if c.strip()]))


async def send_telegram_notify_async(
    chat_id_or_message: str,
    message: Optional[str] = None,
    *,
    parse_mode: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
    timeout: Optional[float] = None,
) -> bool:
    """
    业务通知推荐入口：等待发送完成，外层超时足够覆盖重试，失败只记 WARNING。

    请勿再包一层短 ``wait_for(5)``。
    """
    import asyncio

    wait_sec = timeout
    if wait_sec is None:
        if message is None:
            chat_n = _admin_chat_count()
        else:
            chat_n = max(
                1,
                len([c for c in str(chat_id_or_message or "").split(",") if c.strip()]),
            )
        wait_sec = estimate_telegram_send_timeout_seconds(chat_n)
    try:
        return await asyncio.wait_for(
            send_telegram_message_async(
                chat_id_or_message,
                message,
                parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id,
            ),
            timeout=wait_sec,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "发送 Telegram 通知整体超时（%.0fs），线程内发送可能仍在重试，请检查网络或 api.telegram.org",
            wait_sec,
        )
        return False

_send_lock = threading.Lock()
_last_send_monotonic = 0.0
_last_send_by_chat: Dict[str, float] = {}


def _parse_retry_after(error_msg: str) -> Optional[int]:
    """从 Telegram 429 错误描述中解析 retry_after 秒数。"""
    match = re.search(r"retry after (\d+)", error_msg, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _is_rate_limit_error(error_msg: str) -> bool:
    lowered = error_msg.lower()
    return "429" in error_msg or "too many requests" in lowered


def _is_retryable_network_error(error_msg: str) -> bool:
    lowered = error_msg.lower()
    return (
        "timeout" in lowered
        or "timed out" in lowered
        or "connection" in lowered
        or "network" in lowered
    )


def _get_sync_redis():
    """
    同步 Redis 客户端（懒加载）。

    ``message_sender`` 在线程池/同步路径调用，不能依赖 asyncio Redis 单例。
    不可用时返回 None，降级为进程内间隔。
    """
    global _sync_redis_client, _sync_redis_failed_until
    now = time.monotonic()
    if now < _sync_redis_failed_until:
        return None
    if _sync_redis_client is not None:
        return _sync_redis_client

    with _sync_redis_lock:
        if _sync_redis_client is not None:
            return _sync_redis_client
        if time.monotonic() < _sync_redis_failed_until:
            return None
        host = getattr(settings, "REDIS_HOST", None)
        if not host or not str(host).strip():
            _sync_redis_failed_until = time.monotonic() + _SYNC_REDIS_FAIL_BACKOFF
            return None
        try:
            import redis as redis_sync

            client = redis_sync.Redis(
                host=str(host).strip(),
                port=int(getattr(settings, "REDIS_PORT", 6379) or 6379),
                db=int(getattr(settings, "REDIS_DB", 0) or 0),
                password=getattr(settings, "REDIS_PASSWORD", None) or None,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
                decode_responses=True,
            )
            client.ping()
            _sync_redis_client = client
            return _sync_redis_client
        except Exception as exc:
            _sync_redis_failed_until = time.monotonic() + _SYNC_REDIS_FAIL_BACKOFF
            logger.debug("Telegram 发送限流：同步 Redis 不可用，降级进程内间隔: %s", exc)
            return None


def _redis_wait_seconds(redis_client, key: str) -> float:
    """读取 key 剩余生存时间（秒，支持 PX 亚秒闸门）。"""
    try:
        pttl = redis_client.pttl(key)
        if isinstance(pttl, int) and pttl > 0:
            return pttl / 1000.0
    except Exception:
        global _sync_redis_client, _sync_redis_failed_until
        _sync_redis_client = None
        _sync_redis_failed_until = time.monotonic() + _SYNC_REDIS_FAIL_BACKOFF
    return 0.0


def _note_rate_limited(chat_id: str, retry_after: int) -> None:
    """把 429 退避写入 Redis，让其它 worker 一起停发，避免惊群重试。"""
    wait = max(1, min(int(retry_after), MAX_RATE_LIMIT_WAIT))
    redis_client = _get_sync_redis()
    if not redis_client:
        return
    try:
        redis_client.setex(_REDIS_BACKOFF_GLOBAL, wait, "1")
        redis_client.setex(
            _REDIS_BACKOFF_CHAT.format(chat_id=chat_id),
            wait,
            "1",
        )
    except Exception:
        global _sync_redis_client, _sync_redis_failed_until
        _sync_redis_client = None
        _sync_redis_failed_until = time.monotonic() + _SYNC_REDIS_FAIL_BACKOFF


def _try_acquire_redis_gate(redis_client, key: str, interval_seconds: float) -> bool:
    """NX + PX 闸门：占用成功表示当前进程获得发送权。"""
    px = max(50, int(math.ceil(float(interval_seconds) * 1000)))
    try:
        return bool(redis_client.set(key, str(os.getpid()), nx=True, px=px))
    except Exception:
        global _sync_redis_client, _sync_redis_failed_until
        _sync_redis_client = None
        _sync_redis_failed_until = time.monotonic() + _SYNC_REDIS_FAIL_BACKOFF
        return True  # Redis 异常时放行，仍靠进程内间隔兜底


def _wait_before_send(chat_id: Optional[str] = None) -> None:
    """
    发送前限速：进程内串行 +（可选）Redis 跨进程 per-chat/全局闸门与 429 共享退避。
    """
    global _last_send_monotonic
    chat_key = (str(chat_id).strip() if chat_id else "__default__") or "__default__"
    deadline = time.monotonic() + max(MAX_RATE_LIMIT_WAIT * 2, 30.0)

    while time.monotonic() < deadline:
        sleep_for = 0.0
        redis_client = _get_sync_redis()

        if redis_client:
            sleep_for = max(
                sleep_for,
                _redis_wait_seconds(redis_client, _REDIS_BACKOFF_GLOBAL),
                _redis_wait_seconds(
                    redis_client,
                    _REDIS_BACKOFF_CHAT.format(chat_id=chat_key),
                ),
            )
            if sleep_for <= 0:
                if not _try_acquire_redis_gate(
                    redis_client, _REDIS_GATE_GLOBAL, MIN_GLOBAL_SEND_INTERVAL
                ):
                    sleep_for = max(
                        MIN_GLOBAL_SEND_INTERVAL,
                        _redis_wait_seconds(redis_client, _REDIS_GATE_GLOBAL),
                    )
                elif not _try_acquire_redis_gate(
                    redis_client,
                    _REDIS_GATE_CHAT.format(chat_id=chat_key),
                    MIN_SEND_INTERVAL,
                ):
                    sleep_for = max(
                        0.05,
                        _redis_wait_seconds(
                            redis_client,
                            _REDIS_GATE_CHAT.format(chat_id=chat_key),
                        )
                        or MIN_SEND_INTERVAL,
                    )

        if sleep_for > 0:
            time.sleep(min(sleep_for, float(MAX_RATE_LIMIT_WAIT)))
            continue

        with _send_lock:
            now = time.monotonic()
            elapsed_global = now - _last_send_monotonic
            if elapsed_global < MIN_GLOBAL_SEND_INTERVAL:
                time.sleep(MIN_GLOBAL_SEND_INTERVAL - elapsed_global)
                now = time.monotonic()

            last_chat = _last_send_by_chat.get(chat_key, 0.0)
            elapsed_chat = now - last_chat
            if elapsed_chat < MIN_SEND_INTERVAL:
                time.sleep(MIN_SEND_INTERVAL - elapsed_chat)
                now = time.monotonic()

            _last_send_monotonic = now
            _last_send_by_chat[chat_key] = now
            # 防止字典无限增长
            if len(_last_send_by_chat) > 256:
                oldest = sorted(_last_send_by_chat.items(), key=lambda x: x[1])[:64]
                for k, _ in oldest:
                    _last_send_by_chat.pop(k, None)
        return

    # 超时仍发送：由调用方重试/429 路径兜底
    with _send_lock:
        _last_send_monotonic = time.monotonic()
        _last_send_by_chat[chat_key] = _last_send_monotonic


def _check_bot_available() -> tuple[bool, str]:
    """检查 Bot 是否可用，并返回详细状态信息"""
    # 重新导入模块以获取最新状态
    from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
    from app.core.telegram.bot_state import set_bot_state
    
    if not TELEBOT_AVAILABLE:
        # 动态检查模块是否安装
        try:
            import telebot
            # 更新全局状态
            set_bot_state(bot, bot_initialized, True)
        except ImportError:
            return False, "pyTelegramBotAPI 模块未安装"
    
    # 如果 Bot 未初始化但 token 配置了，创建临时 Bot 实例
    if not bot_initialized or bot is None:
        token = getattr(settings, 'TELEGRAM_TOKEN', None)
        if token and isinstance(token, str) and token.strip():
            try:
                telebot_module = importlib.import_module("telebot")
                # 创建临时 Bot 实例
                temp_bot = telebot_module.TeleBot(token=token)
                # 更新全局状态
                set_bot_state(temp_bot, True, True)
                return True, "Bot 已临时初始化"
            except Exception as e:
                return False, f"Bot 初始化失败: {str(e)}"
        else:
            return False, "Bot 未初始化（无 token）"
    
    return True, "Bot 可用"


def _get_bot_instance():
    """获取 Bot 实例（最新状态）。"""
    from app.core.telegram import bot_state
    return bot_state.bot


def send_telegram_message(
    chat_id_or_message: str,
    message: Optional[str] = None,
    parse_mode: Optional[str] = None,
    reply_to_message_id: Optional[int] = None
) -> bool:
    """
    发送 Telegram 消息（向后兼容版本）
    
    兼容两种调用方式：
    1. 新方式：send_telegram_message(chat_id, message)
    2. 旧方式：send_telegram_message(message)  - 自动使用 TELEGRAM_ADMIN（支持多个 ID，逗号分隔）
    
    Args:
        chat_id_or_message: 聊天 ID（新方式）或消息内容（旧方式）
        message: 消息内容（新方式时必需）
        parse_mode: 解析模式（HTML/Markdown）
        reply_to_message_id: 回复的消息 ID（可选）
    
    Returns:
        bool: 是否发送成功（向所有目标发送成功才返回 True）
    """
    bot_available, status_msg = _check_bot_available()
    if not bot_available:
        logger.warning(f"Bot 不可用，无法发送消息: {status_msg}")
        return False
    
    # 重新导入模块以获取最新状态
    bot = _get_bot_instance()
    
    # 向后兼容：判断是旧方式还是新方式
    if message is None:
        # 旧方式：只有一个参数，即消息内容
        actual_message = chat_id_or_message
        actual_chat_id = getattr(settings, 'TELEGRAM_ADMIN', None)
        if not actual_chat_id:
            logger.warning("TELEGRAM_ADMIN 未设置，无法发送消息")
            return False
    else:
        # 新方式：两个参数；未传 chat_id 时回退 TELEGRAM_ADMIN
        actual_chat_id = chat_id_or_message
        actual_message = message
        if not actual_chat_id or (isinstance(actual_chat_id, str) and not actual_chat_id.strip()):
            actual_chat_id = getattr(settings, 'TELEGRAM_ADMIN', None)

    if not actual_chat_id or (isinstance(actual_chat_id, str) and not str(actual_chat_id).strip()):
        logger.warning("Telegram Chat ID 未设置，无法发送消息")
        return False

    # 截断过长的消息
    if len(actual_message) > MAX_TELEGRAM_MESSAGE_LENGTH:
        truncated_msg = truncate_message(actual_message, MAX_TELEGRAM_MESSAGE_LENGTH)
        logger.info(f"消息过长，已截断：{len(actual_message)} -> {len(truncated_msg)} 字符")
        actual_message = truncated_msg
    
    # 支持逗号分隔的多个 Chat ID，过滤无效 ID（含 str(None) 等）
    chat_ids = [
        cid for cid in (s.strip() for s in str(actual_chat_id).split(","))
        if cid and validate_chat_id(cid)
    ]
    if not chat_ids:
        logger.warning(f"无有效的 Telegram Chat ID，无法发送消息: {actual_chat_id!r}")
        return False

    all_success = True

    for index, chat_id in enumerate(chat_ids):
        if index > 0:
            time.sleep(INTER_CHAT_DELAY)

        # 重试机制
        success = False
        for attempt in range(MAX_RETRIES):
            try:
                _wait_before_send(chat_id)
                bot.send_message(
                    chat_id=chat_id,
                    text=actual_message,
                    reply_to_message_id=reply_to_message_id,
                    timeout=TIMEOUT_SECONDS
                )
                logger.info(f"已发送 Telegram 消息到：{chat_id}（尝试 {attempt + 1}/{MAX_RETRIES}）")
                success = True
                break

            except Exception as e:
                error_msg = str(e)

                if _is_rate_limit_error(error_msg):
                    retry_after = _parse_retry_after(error_msg) or 60
                    retry_after = min(retry_after, MAX_RATE_LIMIT_WAIT)
                    # 先写入共享退避，再 sleep，避免其它 worker 继续打
                    _note_rate_limited(chat_id, retry_after)
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            f"发送 Telegram 消息到 {chat_id} 触发限流，"
                            f"{retry_after}秒后重试（{attempt + 1}/{MAX_RETRIES}）"
                        )
                        time.sleep(retry_after)
                        continue
                    # 可预期限流耗尽：不打 Traceback，避免日志风暴与误报严重故障
                    logger.warning(
                        f"发送 Telegram 消息到 {chat_id} 限流，已达到最大重试次数，消息丢弃：{e}"
                    )
                    all_success = False
                    break

                if _is_retryable_network_error(error_msg):
                    if attempt < MAX_RETRIES - 1:
                        retry_delay = BASE_RETRY_DELAY * (2 ** attempt)
                        logger.warning(
                            f"发送 Telegram 消息到 {chat_id} 超时/网络错误，"
                            f"{retry_delay}秒后重试（{attempt + 1}/{MAX_RETRIES}）：{e}"
                        )
                        time.sleep(retry_delay)
                        continue
                    logger.error(
                        f"发送 Telegram 消息到 {chat_id} 失败，已达到最大重试次数：{e}",
                        exc_info=True
                    )
                    all_success = False
                    break

                logger.error(f"发送 Telegram 消息到 {chat_id} 失败：{e}", exc_info=True)
                all_success = False
                break

        if not success:
            all_success = False

    return all_success


async def send_telegram_message_async(
    chat_id_or_message: str,
    message: Optional[str] = None,
    parse_mode: Optional[str] = None,
    reply_to_message_id: Optional[int] = None
) -> bool:
    """
    异步发送 Telegram 消息（向后兼容版本）
    
    与 send_telegram_message 相同，但在事件循环中运行，支持 await
    
    Args:
        chat_id_or_message: 聊天 ID（新方式）或消息内容（旧方式）
        message: 消息内容（新方式时必需）
        parse_mode: 解析模式（HTML/Markdown）
        reply_to_message_id: 回复的消息 ID（可选）
    
    Returns:
        bool: 是否发送成功
    """
    import asyncio

    return await asyncio.to_thread(
        send_telegram_message,
        chat_id_or_message,
        message,
        parse_mode,
        reply_to_message_id,
    )


def send_telegram_message_with_buttons(
    chat_id: str,
    message: str,
    buttons: List[List[Dict[str, Any]]],
    parse_mode: Optional[str] = None
) -> tuple[bool, Optional[int]]:
    """
    发送带内联按钮的 Telegram 消息
    
    Args:
        chat_id: 聊天 ID
        message: 消息内容
        buttons: 按钮列表 [[{text, callback_data}], ...]
        parse_mode: 解析模式（HTML/Markdown）
    
    Returns:
        tuple[bool, Optional[int]]: (是否发送成功, 消息ID)
    """
    bot_available, status_msg = _check_bot_available()
    if not bot_available:
        logger.warning(f"Bot 不可用，无法发送消息: {status_msg}")
        return False, None

    if not chat_id or not validate_chat_id(str(chat_id).strip()):
        logger.warning(f"无效的 Telegram Chat ID，无法发送带按钮消息: {chat_id!r}")
        return False, None
    
    # 重新导入模块以获取最新状态
    bot = _get_bot_instance()
    
    try:
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        # 构建内联键盘
        keyboard = []
        for row in buttons:
            button_row = []
            for btn in row:
                button = InlineKeyboardButton(
                    text=btn.get('text', ''),
                    callback_data=btn.get('callback_data', '')
                )
                button_row.append(button)
            keyboard.append(button_row)
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(*[btn for row in keyboard for btn in row])
        
        # 截断过长的消息
        if len(message) > MAX_TELEGRAM_MESSAGE_LENGTH:
            truncated_msg = truncate_message(message, MAX_TELEGRAM_MESSAGE_LENGTH)
            message = truncated_msg
        
        # 重试机制
        for attempt in range(MAX_RETRIES):
            try:
                _wait_before_send(chat_id)
                sent_message = bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    reply_markup=markup,
                    timeout=TIMEOUT_SECONDS
                )
                logger.info(f"已发送带按钮的 Telegram 消息到：{chat_id}（尝试 {attempt + 1}/{MAX_RETRIES}）")
                return True, sent_message.message_id

            except Exception as e:
                error_msg = str(e)

                if _is_rate_limit_error(error_msg):
                    retry_after = _parse_retry_after(error_msg) or 60
                    retry_after = min(retry_after, MAX_RATE_LIMIT_WAIT)
                    _note_rate_limited(str(chat_id), retry_after)
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            f"发送带按钮的 Telegram 消息触发限流，"
                            f"{retry_after}秒后重试（{attempt + 1}/{MAX_RETRIES}）"
                        )
                        time.sleep(retry_after)
                        continue
                    logger.warning(
                        f"发送带按钮的 Telegram 消息限流，已达到最大重试次数，消息丢弃：{e}"
                    )
                    return False, None

                if _is_retryable_network_error(error_msg):
                    if attempt < MAX_RETRIES - 1:
                        retry_delay = BASE_RETRY_DELAY * (2 ** attempt)
                        logger.warning(
                            f"发送带按钮的 Telegram 消息超时/网络错误，"
                            f"{retry_delay}秒后重试（{attempt + 1}/{MAX_RETRIES}）：{e}"
                        )
                        time.sleep(retry_delay)
                        continue
                    logger.error(
                        f"发送带按钮的 Telegram 消息失败，已达到最大重试次数：{e}",
                        exc_info=True
                    )
                    return False, None

                logger.error(f"发送带按钮的 Telegram 消息失败：{e}", exc_info=True)
                return False, None
        
    except Exception as e:
        logger.error(f"构建带按钮的 Telegram 消息失败：{e}", exc_info=True)
        return False, None


async def send_admin_notification(
    message: str,
    telegram_chat_id: str,
    notification_type: str = 'system',
    db: Optional[Any] = None
) -> bool:
    """
    发送管理员通知
    
    Args:
        message: 通知内容
        telegram_chat_id: 管理员 Chat ID
        notification_type: 通知类型（system/conversion/forward_failure 等）
        db: 数据库会话（可选）
    
    Returns:
        bool: 是否发送成功
    """
    if not telegram_chat_id:
        logger.warning("Telegram Chat ID 未设置，无法发送管理员通知")
        return False
    
    # 添加通知类型前缀
    type_prefixes = {
        'system': '⚠️ ',
        'conversion': '💰 ',
        'forward_failure': '❌ ',
        'forward_success': '✅ ',
        'statistics': '📊 '
    }
    
    prefix = type_prefixes.get(notification_type, '🔔 ')
    full_message = f"{prefix}{message}"
    
    return send_telegram_message(telegram_chat_id, full_message)
