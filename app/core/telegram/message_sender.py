"""
Telegram 消息发送模块

提供消息发送功能，包括普通消息、带按钮消息和管理员通知
"""
import logging
import time
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.telegram.bot_state import bot, bot_initialized, TELEBOT_AVAILABLE
from app.core.telegram_utils import truncate_message, MAX_TELEGRAM_MESSAGE_LENGTH
from app.core.config import settings

logger = logging.getLogger(__name__)

# 消息发送配置
MAX_RETRIES = 3  # 最大重试次数
BASE_RETRY_DELAY = 2  # 基础重试延迟（秒）
TIMEOUT_SECONDS = 15  # 超时时间（秒）


def _check_bot_available() -> tuple[bool, str]:
    """检查 Bot 是否可用，并返回详细状态信息"""
    if not TELEBOT_AVAILABLE:
        return False, "pyTelegramBotAPI 模块未安装"
    if not bot_initialized:
        return False, "Bot 未初始化"
    if bot is None:
        return False, "Bot 实例为 None"
    return True, "Bot 可用"


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
    2. 旧方式：send_telegram_message(message)  - 自动使用 TELEGRAM_ADMIN
    
    Args:
        chat_id_or_message: 聊天 ID（新方式）或消息内容（旧方式）
        message: 消息内容（新方式时必需）
        parse_mode: 解析模式（HTML/Markdown）
        reply_to_message_id: 回复的消息 ID（可选）
    
    Returns:
        bool: 是否发送成功
    """
    bot_available, status_msg = _check_bot_available()
    if not bot_available:
        logger.warning(f"Bot 不可用，无法发送消息: {status_msg}")
        return False
    
    # 向后兼容：判断是旧方式还是新方式
    if message is None:
        # 旧方式：只有一个参数，即消息内容
        actual_message = chat_id_or_message
        actual_chat_id = getattr(settings, 'TELEGRAM_ADMIN', None)
        if not actual_chat_id:
            logger.warning("TELEGRAM_ADMIN 未设置，无法发送消息")
            return False
    else:
        # 新方式：两个参数
        actual_chat_id = chat_id_or_message
        actual_message = message
    
    # 截断过长的消息
    if len(actual_message) > MAX_TELEGRAM_MESSAGE_LENGTH:
        truncated_msg = truncate_message(actual_message, MAX_TELEGRAM_MESSAGE_LENGTH)
        logger.info(f"消息过长，已截断：{len(actual_message)} -> {len(truncated_msg)} 字符")
        actual_message = truncated_msg
    
    # 重试机制
    for attempt in range(MAX_RETRIES):
        try:
            # 发送消息，不使用 parse_mode 以避免 HTML 解析错误
            # 设置超时参数
            bot.send_message(
                chat_id=actual_chat_id,
                text=actual_message,
                reply_to_message_id=reply_to_message_id,
                timeout=TIMEOUT_SECONDS
            )
            logger.info(f"已发送 Telegram 消息到：{actual_chat_id}（尝试 {attempt + 1}/{MAX_RETRIES}）")
            return True
            
        except Exception as e:
            error_msg = str(e)
            is_timeout = 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower()
            is_network_error = 'connection' in error_msg.lower() or 'network' in error_msg.lower()
            
            if is_timeout or is_network_error:
                # 网络相关错误，进行重试
                if attempt < MAX_RETRIES - 1:
                    retry_delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"发送 Telegram 消息超时/网络错误，{retry_delay}秒后重试（{attempt + 1}/{MAX_RETRIES}）：{e}")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"发送 Telegram 消息失败，已达到最大重试次数：{e}", exc_info=True)
                    return False
            else:
                # 其他错误，直接返回失败
                logger.error(f"发送 Telegram 消息失败：{e}", exc_info=True)
                return False


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
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: send_telegram_message(
            chat_id_or_message,
            message,
            parse_mode,
            reply_to_message_id
        )
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
                is_timeout = 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower()
                is_network_error = 'connection' in error_msg.lower() or 'network' in error_msg.lower()
                
                if is_timeout or is_network_error:
                    # 网络相关错误，进行重试
                    if attempt < MAX_RETRIES - 1:
                        retry_delay = BASE_RETRY_DELAY * (2 ** attempt)
                        logger.warning(f"发送带按钮的 Telegram 消息超时/网络错误，{retry_delay}秒后重试（{attempt + 1}/{MAX_RETRIES}）：{e}")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error(f"发送带按钮的 Telegram 消息失败，已达到最大重试次数：{e}", exc_info=True)
                        return False, None
                else:
                    # 其他错误，直接返回失败
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
