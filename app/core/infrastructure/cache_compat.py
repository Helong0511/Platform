"""
缓存兼容层
保持与旧 cache.py 的兼容性，同时使用新的缓存抽象层（带监控）
"""
import json
import hashlib
import time
import logging
from typing import Any, Optional

from app.core.infrastructure.cache import get_cache_backend
from app.core.infrastructure.cache_metrics import get_metrics_collector

logger = logging.getLogger(__name__)


async def get_cached(key: str, key_prefix: str = 'global') -> Optional[Any]:
    """
    兼容旧接口：获取缓存（带监控）
    
    Args:
        key: 缓存键
        key_prefix: 指标前缀（用于分类统计）
    
    Returns:
        缓存值或 None
    """
    start_time = time.time()
    cache = await get_cache_backend()
    metrics = get_metrics_collector()
    
    try:
        value = await cache.get(key)
        response_time_ms = (time.time() - start_time) * 1000
        
        if value is not None:
            logger.debug(f"缓存命中：key={key}, response_time={response_time_ms:.2f}ms")
            metrics.record_hit(key_prefix, response_time_ms)
        else:
            logger.debug(f"缓存未命中：key={key}, response_time={response_time_ms:.2f}ms")
            metrics.record_miss(key_prefix, response_time_ms)
        
        return value
    
    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        logger.error(f"获取缓存失败：key={key}, error={e}", exc_info=True)
        metrics.record_error(key_prefix)
        return None


async def set_cached(key: str, value: Any, ttl: int = 300, key_prefix: str = 'global') -> bool:
    """
    兼容旧接口：设置缓存（带监控）
    
    Args:
        key: 缓存键
        value: 缓存值
        ttl: TTL（秒）
        key_prefix: 指标前缀
    
    Returns:
        是否成功
    """
    start_time = time.time()
    cache = await get_cache_backend()
    metrics = get_metrics_collector()
    
    try:
        result = await cache.set(key, value, ttl=ttl)
        response_time_ms = (time.time() - start_time) * 1000
        
        logger.debug(f"设置缓存成功：key={key}, ttl={ttl}s, response_time={response_time_ms:.2f}ms")
        return result
    
    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        logger.error(f"设置缓存失败：key={key}, error={e}", exc_info=True)
        metrics.record_error(key_prefix)
        return False


def generate_cache_key(*args, **kwargs) -> str:
    """
    兼容旧接口：生成缓存键
    
    Args:
        *args: 位置参数
        **kwargs: 关键字参数
    
    Returns:
        MD5 哈希的缓存键
    """
    key_str = json.dumps(
        {"args": args, "kwargs": kwargs},
        sort_keys=True,
        default=str
    )
    return hashlib.md5(key_str.encode()).hexdigest()
