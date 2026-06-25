"""
Telegram 消息发送模块

提供消息发送功能，包括普通消息、带按钮消息和管理员通知
"""
import logging
import importlib
import re
import threading
import time
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.telegram_utils import truncate_message, MAX_TELEGRAM_MESSAGE_LENGTH, validate_chat_id
from app.core.config import settings

logger = logging.getLogger(__name__)

# 消息发送配置
MAX_RETRIES = 3  # 最大重试次数
BASE_RETRY_DELAY = 2  # 基础重试延迟（秒）
TIMEOUT_SECONDS = 15  # 超时时间（秒）
INTER_CHAT_DELAY = 0.35  # 同一批次向多个 Chat ID 发送时的间隔（秒）
MIN_SEND_INTERVAL = 0.05  # 全局最小发送间隔（秒）
MAX_RATE_LIMIT_WAIT = 120  # 429 限流时最长等待秒数

_send_lock = threading.Lock()
_last_send_monotonic = 0.0


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


def _wait_before_send() -> None:
    """全局串行化发送并保证最小间隔，避免多线程并发触发限流。"""
    global _last_send_monotonic
    with _send_lock:
        elapsed = time.monotonic() - _last_send_monotonic
        if elapsed < MIN_SEND_INTERVAL:
            time.sleep(MIN_SEND_INTERVAL - elapsed)
        _last_send_monotonic = time.monotonic()


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
                _wait_before_send()
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
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            f"发送 Telegram 消息到 {chat_id} 触发限流，"
                            f"{retry_after}秒后重试（{attempt + 1}/{MAX_RETRIES}）"
                        )
                        time.sleep(retry_after)
                        continue
                    logger.error(
                        f"发送 Telegram 消息到 {chat_id} 限流，已达到最大重试次数：{e}",
                        exc_info=True
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
                _wait_before_send()
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
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            f"发送带按钮的 Telegram 消息触发限流，"
                            f"{retry_after}秒后重试（{attempt + 1}/{MAX_RETRIES}）"
                        )
                        time.sleep(retry_after)
                        continue
                    logger.error(
                        f"发送带按钮的 Telegram 消息限流，已达到最大重试次数：{e}",
                        exc_info=True
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
