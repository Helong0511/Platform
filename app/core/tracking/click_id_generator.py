"""
Click ID 生成器
用于生成唯一的点击ID，用于CPL系统的点击追踪
"""
import string
import random
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 排除容易混淆的字符：0, O, o, I, l, 1, 2, 5, 6, 8, u, v, U, V, Z, S, G, B, Q, D
# 保留的字符：3, 4, 7, 9, a-h, j-k, m, n, p-r, t, w-z, A-H, J-K, M, N, P-R, T, W-X, Y
CLICK_ID_CHARS = (
    '3479' +  # 数字（排除0,1,2,5,6,8）
    'abcdefghjkmnprtwxyz' +  # 小写字母（排除o, i, l, u, v, s, q, d）
    'ABCDEFGHJKMNPRTWXY'  # 大写字母（排除O, I, Z, S, G, B, Q, D, U, V）
)
CLICK_ID_BASE = len(CLICK_ID_CHARS)


def generate_click_id(length: int = 32) -> str:
    """
    生成随机点击ID
    
    Args:
        length: ID长度（默认32位）
        
    Returns:
        随机生成的点击ID
    """
    return ''.join(random.choices(CLICK_ID_CHARS, k=length))


def generate_unique_click_id(
    existing_ids: set,
    length: int = 32,
    max_attempts: int = 100
) -> Optional[str]:
    """
    生成唯一的点击ID
    
    Args:
        existing_ids: 已存在的ID集合
        length: ID长度
        max_attempts: 最大尝试次数
        
    Returns:
        唯一的点击ID，如果生成失败返回 None
    """
    for _ in range(max_attempts):
        click_id = generate_click_id(length)
        if click_id not in existing_ids:
            return click_id
    
    logger.warning(f"生成唯一点击ID失败，已尝试 {max_attempts} 次")
    return None


def generate_click_id_from_timestamp() -> str:
    """
    基于时间戳生成点击ID（确保唯一性）
    
    Returns:
        基于时间戳的点击ID
    """
    # 获取当前时间戳（微秒级）
    timestamp = datetime.now(timezone.utc).timestamp() * 1000000  # 转换为微秒
    timestamp_int = int(timestamp)
    
    # 转换为Base62-like编码（使用我们的字符集）
    if timestamp_int == 0:
        return CLICK_ID_CHARS[0]
    
    result = []
    num = timestamp_int
    while num > 0:
        result.append(CLICK_ID_CHARS[num % CLICK_ID_BASE])
        num //= CLICK_ID_BASE
    
    base_id = ''.join(reversed(result))
    
    # 如果长度不足，前面补随机字符
    if len(base_id) < 16:
        padding_length = 16 - len(base_id)
        padding = ''.join(random.choices(CLICK_ID_CHARS, k=padding_length))
        base_id = padding + base_id
    
    # 添加随机后缀确保唯一性
    random_suffix = ''.join(random.choices(CLICK_ID_CHARS, k=16))
    
    return base_id + random_suffix

