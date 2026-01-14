"""
Telegram 消息工具模块
提供 Telegram 消息格式化、分割、验证等实用功能
"""
import json
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Telegram 消息最大长度（字符）
MAX_TELEGRAM_MESSAGE_LENGTH = 4096

# 消息截断时保留的提示信息长度
TRUNCATE_NOTICE_LENGTH = 100


def truncate_message(message: str, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> str:
    """
    截断消息，确保不超过 Telegram 的最大长度限制
    
    Args:
        message: 原始消息
        max_length: 最大长度（默认 4096）
    
    Returns:
        截断后的消息
    """
    if len(message) <= max_length:
        return message
    
    # 截断消息，保留重要信息
    truncated_msg = message[:max_length - TRUNCATE_NOTICE_LENGTH]
    truncated_msg += f"\n\n... (消息过长，已截断，原始长度: {len(message)} 字符)"
    
    logger.warning(f"Telegram 消息过长 ({len(message)} 字符)，已截断为 {len(truncated_msg)} 字符")
    return truncated_msg


def split_long_message(message: str, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> List[str]:
    """
    将长消息分割为多条消息
    
    如果消息超过最大长度，会按段落或行分割为多条消息
    
    Args:
        message: 原始消息
        max_length: 每条消息的最大长度（默认 4096）
    
    Returns:
        消息列表（如果不需要分割，返回包含一条消息的列表）
    """
    if len(message) <= max_length:
        return [message]
    
    messages = []
    lines = message.split('\n')
    current_message = ""
    part_number = 1
    total_parts = None  # 先计算总部分数
    
    # 先估算需要分割成几部分
    estimated_parts = (len(message) // max_length) + 1
    
    for line in lines:
        # 如果当前行加上当前消息会超过限制
        if current_message and len(current_message) + len(line) + 1 > max_length:
            # 保存当前消息
            if current_message:
                messages.append(current_message.strip())
                current_message = ""
                part_number += 1
        
        # 如果单行就超过限制，需要截断
        if len(line) > max_length - 50:  # 保留一些空间给提示信息
            # 截断这一行
            truncated_line = line[:max_length - 50] + "..."
            if current_message:
                messages.append(current_message.strip())
                current_message = ""
                part_number += 1
            current_message = truncated_line
        else:
            # 添加这一行
            if current_message:
                current_message += "\n" + line
            else:
                current_message = line
    
    # 添加最后一部分
    if current_message:
        messages.append(current_message.strip())
    
    # 如果分割成了多条消息，为每条消息添加序号
    if len(messages) > 1:
        formatted_messages = []
        for i, msg in enumerate(messages, 1):
            header = f"📄 消息 {i}/{len(messages)}\n\n"
            # 确保加上序号后不超过限制
            if len(header) + len(msg) <= max_length:
                formatted_messages.append(header + msg)
            else:
                # 如果加上序号后超过限制，截断消息内容
                available_length = max_length - len(header) - 20  # 保留一些空间
                truncated_msg = msg[:available_length] + "..."
                formatted_messages.append(header + truncated_msg)
        return formatted_messages
    
    return messages


def format_telegram_message(
    title: str,
    fields: Optional[dict] = None,
    footer: Optional[str] = None,
    max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH
) -> str:
    """
    格式化 Telegram 消息（统一格式）
    
    Args:
        title: 消息标题（带 emoji）
        fields: 字段字典 {key: value}
        footer: 页脚信息
        max_length: 最大长度
    
    Returns:
        格式化后的消息
    """
    message = f"{title}\n\n"
    
    if fields:
        for key, value in fields.items():
            if value is not None:
                # 格式化值
                if isinstance(value, (dict, list)):
                    try:
                        value_str = json.dumps(value, ensure_ascii=False, indent=2)
                    except:
                        value_str = str(value)
                else:
                    value_str = str(value)
                
                # 限制单个字段值的长度
                if len(value_str) > 200:
                    value_str = value_str[:200] + "..."
                
                message += f"{key}: {value_str}\n"
    
    if footer:
        message += f"\n{footer}"
    
    # 检查并截断消息
    if len(message) > max_length:
        message = truncate_message(message, max_length)
    
    return message


def validate_chat_id(chat_id: str) -> bool:
    """
    验证 Telegram Chat ID 格式
    
    Args:
        chat_id: Chat ID 字符串
    
    Returns:
        是否有效
    """
    if not chat_id or not isinstance(chat_id, str):
        return False
    
    chat_id = chat_id.strip()
    
    # Chat ID 应该是数字字符串（可能带负号，用于群组）
    # 用户 ID: 纯数字，如 "123456789"
    # 群组 ID: 负号 + 数字，如 "-1001234567890"
    if chat_id.startswith('-'):
        # 群组 ID
        return chat_id[1:].isdigit()
    else:
        # 用户 ID
        return chat_id.isdigit()


def escape_markdown_v2(text: str) -> str:
    """
    转义 Markdown V2 特殊字符
    
    Args:
        text: 原始文本
    
    Returns:
        转义后的文本
    """
    # Markdown V2 需要转义的字符
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def format_key_value_pairs(data: dict, max_value_length: int = 150) -> str:
    """
    格式化键值对为消息文本
    
    Args:
        data: 数据字典
        max_value_length: 单个值的最大长度
    
    Returns:
        格式化后的文本
    """
    if not data:
        return "无数据"
    
    lines = []
    for key, value in sorted(data.items()):
        # 格式化值
        if value is None:
            value_str = "None"
        elif isinstance(value, (dict, list)):
            try:
                value_str = json.dumps(value, ensure_ascii=False)
            except:
                value_str = str(value)
        else:
            value_str = str(value)
        
        # 限制值的长度
        if len(value_str) > max_value_length:
            value_str = value_str[:max_value_length] + "..."
        
        lines.append(f"• {key}: {value_str}")
    
    return "\n".join(lines)

