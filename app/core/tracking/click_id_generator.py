"""
Click ID 生成器
用于生成唯一的点击ID，用于CPL系统的点击追踪
"""
import string
import random
import logging
import os
import threading
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

# 线程本地存储，用于维护每个线程的计数器
_thread_local = threading.local()

def _get_thread_counter() -> int:
    """获取当前线程的计数器并递增"""
    if not hasattr(_thread_local, 'counter'):
        _thread_local.counter = 0
    _thread_local.counter += 1
    return _thread_local.counter


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


def _encode_base(num: int) -> str:
    """将数字转换为Base编码（使用我们的字符集）"""
    if num == 0:
        return CLICK_ID_CHARS[0]
    result = []
    while num > 0:
        result.append(CLICK_ID_CHARS[num % CLICK_ID_BASE])
        num //= CLICK_ID_BASE
    return ''.join(reversed(result))


def generate_click_id_from_timestamp() -> str:
    """
    基于时间戳生成点击ID（确保唯一性）
    
    改进版本，增加了以下唯一性保证：
    1. 使用微秒级时间戳（主要部分）
    2. 添加进程ID（多进程环境下区分，取后4位）
    3. 添加线程ID（多线程环境下区分，取后4位）
    4. 添加线程本地计数器（同一线程内同一时间戳的区分，0-999）
    5. 增加随机后缀长度（从16位增加到24位，提高唯一性）
    
    Returns:
        基于时间戳的点击ID（总长度约40-50位）
    """
    # 获取当前时间戳（微秒级）
    now = datetime.now(timezone.utc)
    timestamp_us = int(now.timestamp() * 1000000)  # 微秒级时间戳
    
    # 获取进程ID和线程ID
    process_id = os.getpid()
    thread_id = threading.get_ident()
    
    # 获取线程本地计数器（用于同一线程内同一时间戳的区分）
    thread_counter = _get_thread_counter()
    
    # 编码各个组件
    timestamp_part = _encode_base(timestamp_us)
    process_part = _encode_base(process_id % 10000)  # 取后4位
    thread_part = _encode_base(thread_id % 10000)  # 取后4位
    counter_part = _encode_base(thread_counter % 1000)  # 取后3位（0-999）
    
    # 组合各部分（时间戳 + 进程 + 线程 + 计数器）
    base_id = timestamp_part + process_part + thread_part + counter_part
    
    # 如果总长度不足16，前面补随机字符
    if len(base_id) < 16:
        padding_length = 16 - len(base_id)
        padding = ''.join(random.choices(CLICK_ID_CHARS, k=padding_length))
        base_id = padding + base_id
    elif len(base_id) > 32:
        # 如果太长，截取前32位
        base_id = base_id[:32]
    
    # 添加更长的随机后缀确保唯一性（从16位增加到24位）
    random_suffix = ''.join(random.choices(CLICK_ID_CHARS, k=24))
    
    return base_id + random_suffix


def generate_click_id_unified(
    *,
    offer_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    short_link_id: Optional[int] = None,
    url_params: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> str:
    """
    统一生成入口（延迟导入，避免循环依赖）。

    USE_TRACKING_TOKEN=false 时与 ``generate_click_id_from_timestamp`` 行为一致。
    """
    from app.core.tracking.click_token import generate_click_id_unified as _gen

    return _gen(
        offer_id=offer_id,
        publisher_id=publisher_id,
        advertiser_id=advertiser_id,
        short_link_id=short_link_id,
        url_params=url_params,
        extra=extra,
    )

