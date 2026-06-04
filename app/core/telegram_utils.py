"""
Telegram 消息工具模块
提供 Telegram 消息格式化、分割、验证等实用功能
"""
import json
import logging
import re
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

logger = logging.getLogger(__name__)

# Telegram 消息最大长度（字符）
MAX_TELEGRAM_MESSAGE_LENGTH = 4096

# 消息截断时保留的提示信息长度
TRUNCATE_NOTICE_LENGTH = 100

# Telegram 消息类型
MESSAGE_TYPES = {
    'info': 'ℹ️',
    'success': '✅',
    'warning': '⚠️',
    'error': '❌',
    'conversion': '📊',
    'high_value': '💰',
    'notification': '🔔',
    'stats': '📈',
    'alert': '🚨'
}


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
    fields: Optional[Dict[str, Any]] = None,
    footer: Optional[str] = None,
    max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH,
    message_type: Optional[str] = None
) -> str:
    """
    格式化 Telegram 消息（统一格式）
    
    Args:
        title: 消息标题（带 emoji）
        fields: 字段字典 {key: value}
        footer: 页脚信息
        max_length: 最大长度
        message_type: 消息类型（用于自动添加 emoji）
    
    Returns:
        格式化后的消息
    """
    # 如果指定了消息类型，自动添加对应 emoji
    if message_type and message_type in MESSAGE_TYPES:
        emoji = MESSAGE_TYPES[message_type]
        if not title.startswith(emoji):
            title = f"{emoji} {title}"
    
    message = f"{title}\n\n"
    
    if fields:
        for key, value in fields.items():
            if value is not None:
                # 格式化值
                value_str = format_value(value)
                
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


def format_value(value: Any) -> str:
    """
    格式化值为字符串
    
    Args:
        value: 任意类型的值
    
    Returns:
        格式化后的字符串
    """
    if value is None:
        return "None"
    elif isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(value)
    elif isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(value, bool):
        return "是" if value else "否"
    elif isinstance(value, float):
        # 保留 2 位小数
        return f"{value:.2f}"
    else:
        return str(value)


def validate_chat_id(chat_id: Union[str, int]) -> bool:
    """
    验证 Telegram Chat ID 格式
    
    Args:
        chat_id: Chat ID 字符串或整数
    
    Returns:
        是否有效
    """
    if chat_id is None:
        return False
    
    # 如果是整数，转换为字符串
    if isinstance(chat_id, int):
        chat_id = str(chat_id)
    
    if not isinstance(chat_id, str):
        return False
    
    chat_id = chat_id.strip()
    
    if not chat_id:
        return False
    
    # Chat ID 应该是数字字符串（可能带负号，用于群组）
    # 用户 ID: 纯数字，如 "123456789"
    # 群组 ID: 负号 + 数字，如 "-1001234567890"
    if chat_id.startswith('-'):
        # 群组 ID
        return chat_id[1:].isdigit()
    else:
        # 用户 ID
        return chat_id.isdigit()


def parse_chat_id(chat_id: Union[str, int]) -> Optional[int]:
    """
    解析 Chat ID 为整数
    
    Args:
        chat_id: Chat ID 字符串或整数
    
    Returns:
        Chat ID 整数，如果无效则返回 None
    """
    if validate_chat_id(chat_id):
        return int(str(chat_id).strip())
    return None


def escape_markdown_v2(text: str) -> str:
    """
    转义 Markdown V2 特殊字符
    
    Args:
        text: 原始文本
    
    Returns:
        转义后的文本
    """
    if not text:
        return ""
    
    # Markdown V2 需要转义的字符
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    result = text
    for char in special_chars:
        result = result.replace(char, f'\\{char}')
    
    return result


def escape_html(text: str) -> str:
    """
    转义 HTML 特殊字符
    
    Args:
        text: 原始文本
    
    Returns:
        转义后的文本
    """
    if not text:
        return ""
    
    html_entities = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }
    
    result = text
    for char, entity in html_entities.items():
        result = result.replace(char, entity)
    
    return result


def format_key_value_pairs(
    data: Dict[str, Any],
    max_value_length: int = 150,
    bullet: str = "•"
) -> str:
    """
    格式化键值对为消息文本
    
    Args:
        data: 数据字典
        max_value_length: 单个值的最大长度
        bullet: 项目符号
    
    Returns:
        格式化后的文本
    """
    if not data:
        return "无数据"
    
    lines = []
    for key, value in sorted(data.items()):
        # 格式化值
        value_str = format_value(value)
        
        # 限制值的长度
        if len(value_str) > max_value_length:
            value_str = value_str[:max_value_length] + "..."
        
        lines.append(f"{bullet} {key}: {value_str}")
    
    return "\n".join(lines)


def format_stats_table(
    data: List[Dict[str, Any]],
    columns: List[str],
    column_names: Optional[List[str]] = None
) -> str:
    """
    格式化简单的统计表格（用于 Telegram 消息）
    
    Args:
        data: 数据列表
        columns: 要显示的列名
        column_names: 可选的列显示名称
    
    Returns:
        格式化后的表格文本
    """
    if not data:
        return "暂无数据"
    
    if column_names and len(column_names) != len(columns):
        column_names = None
    
    result = ""
    
    # 添加表头
    headers = column_names if column_names else columns
    result += " | ".join(headers) + "\n"
    result += "-" * (len(" | ".join(headers)) + 4) + "\n"
    
    # 添加数据行
    for item in data:
        row = []
        for col in columns:
            value = item.get(col, "-")
            row.append(format_value(value))
        result += " | ".join(row) + "\n"
    
    return result


def extract_chat_id_from_text(text: str) -> Optional[str]:
    """
    从文本中提取可能的 Chat ID
    
    Args:
        text: 包含 Chat ID 的文本
    
    Returns:
        提取的 Chat ID，如果没有找到则返回 None
    """
    if not text:
        return None
    
    # 匹配可能的 Chat ID 模式
    # 支持: -1001234567890, 123456789, id:123456, ID=123456 等
    patterns = [
        r'(?<!\w)(-?\d{8,})(?!\w)',  # 纯数字，至少 8 位
        r'id[:\s=]+(-?\d+)',  # id: 12345 或 id=12345
        r'chat[:\s=]+(-?\d+)',  # chat: 12345 或 chat=12345
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            chat_id = match.group(1)
            if validate_chat_id(chat_id):
                return chat_id
    
    return None


def build_conversion_message(
    conversion_data: Dict[str, Any],
    message_type: str = 'conversion',
    include_details: bool = True
) -> str:
    """
    构建转化通知消息
    
    Args:
        conversion_data: 转化数据字典
        message_type: 消息类型
        include_details: 是否包含详细信息
    
    Returns:
        格式化的消息
    """
    emoji = MESSAGE_TYPES.get(message_type, '📊')
    
    title = f"{emoji} 转化通知"
    if message_type == 'high_value':
        title = f"{emoji} 高价值转化通知"
    
    fields = {}
    
    # 基础信息
    if 'conversion_id' in conversion_data:
        fields['转化ID'] = conversion_data['conversion_id']
    if 'platform' in conversion_data:
        fields['平台'] = conversion_data['platform']
    if 'event_name' in conversion_data:
        fields['事件'] = conversion_data['event_name']
    
    # 金额信息
    if 'original_payout' in conversion_data:
        fields['原始金额'] = f"${conversion_data['original_payout']:.2f}"
    if 'payout' in conversion_data:
        fields['扣后金额'] = f"${conversion_data['payout']:.2f}"
    if 'high_value_threshold' in conversion_data:
        fields['阈值'] = f"${conversion_data['high_value_threshold']:.2f} ✅"
    
    # 详细信息（可选）
    if include_details:
        if 'client_name' in conversion_data:
            fields['客户'] = conversion_data['client_name']
        if 'product_name' in conversion_data:
            fields['产品'] = conversion_data['product_name']
        if 'publisher_name' in conversion_data:
            fields['渠道'] = conversion_data['publisher_name']
        if 'offer_name' in conversion_data:
            fields['Offer'] = conversion_data['offer_name']
    
    # 时间
    footer = None
    if 'created_at' in conversion_data:
        if isinstance(conversion_data['created_at'], datetime):
            time_str = conversion_data['created_at'].strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = str(conversion_data['created_at'])
        footer = f"⏰ 时间: {time_str}"
    
    return format_telegram_message(
        title=title,
        fields=fields,
        footer=footer,
        message_type=message_type
    )


def build_summary_message(
    summary_data: Dict[str, Any],
    period: str = 'today'
) -> str:
    """
    构建汇总统计消息
    
    Args:
        summary_data: 汇总数据字典
        period: 统计周期（today, weekly, monthly）
    
    Returns:
        格式化的消息
    """
    period_names = {
        'today': '今日',
        'weekly': '本周',
        'monthly': '本月',
        'hourly': '每小时',
        'daily': '每日'
    }
    
    period_name = period_names.get(period, period)
    
    title = f"📊 {period_name}统计汇总"
    
    fields = {}
    
    if 'total_clicks' in summary_data:
        fields['总点击'] = summary_data['total_clicks']
    if 'total_conversions' in summary_data:
        fields['总转化'] = summary_data['total_conversions']
    if 'cr' in summary_data:
        fields['转化率'] = f"{summary_data['cr']:.2f}%"
    if 'total_payout' in summary_data:
        fields['总收益'] = f"${summary_data['total_payout']:.2f}"
    if 'total_profit' in summary_data:
        fields['总利润'] = f"${summary_data['total_profit']:.2f}"
    
    # 添加时间信息
    footer = None
    if 'start_date' in summary_data and 'end_date' in summary_data:
        footer = f"📅 时间范围: {summary_data['start_date']} 至 {summary_data['end_date']}"
    
    return format_telegram_message(
        title=title,
        fields=fields,
        footer=footer,
        message_type='stats'
    )


def build_alert_message(
    alert_type: str,
    description: str,
    location: Optional[Dict[str, str]] = None,
    error: Optional[Exception] = None
) -> str:
    """
    构建告警消息
    
    Args:
        alert_type: 告警类型
        description: 告警描述
        location: 位置信息（模块、函数、行号等）
        error: 异常对象（可选）
    
    Returns:
        格式化的告警消息
    """
    title = f"🚨 系统告警: {alert_type}"
    
    fields = {'描述': description}
    
    if location:
        if 'module' in location:
            fields['模块'] = location['module']
        if 'function' in location:
            fields['函数'] = location['function']
        if 'line' in location:
            fields['行号'] = location['line']
        if 'file' in location:
            fields['文件'] = location['file']
    
    if error:
        fields['错误类型'] = type(error).__name__
        fields['错误信息'] = str(error)[:200]
    
    # 添加时间
    footer = f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    return format_telegram_message(
        title=title,
        fields=fields,
        footer=footer,
        message_type='alert'
    )

