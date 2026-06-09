"""
查询结果缓存工具模块。

职责：为业务查询提供 Redis 键值缓存（命中则跳过 DB/计算），Redis 不可用时静默降级、不影响主流程。

在系统中的位置：``app.core.cache``，被 Dashboard、统计类 API 等通过 ``@cache_query`` 或
``get_or_set_cache`` 调用；底层依赖 ``app.core.redis_client``。
"""
from app.core.redis_client import get_redis_client
import json
import hashlib
import logging
from typing import Any, Optional, Callable
from functools import wraps

logger = logging.getLogger(__name__)

CACHE_PREFIX = "query_cache:"
DEFAULT_TTL = 300  # 默认 5 分钟


def generate_cache_key(*args, **kwargs) -> str:
    """
    生成缓存键
    
    Args:
        *args: 位置参数
        **kwargs: 关键字参数
    
    Returns:
        str: MD5 哈希后的缓存键
    """
    # 将参数序列化为 JSON 字符串，确保相同参数生成相同键
    key_str = json.dumps(
        {"args": args, "kwargs": kwargs},
        sort_keys=True,
        default=str
    )
    return hashlib.md5(key_str.encode()).hexdigest()


async def get_cached(key: str) -> Optional[Any]:
    """
    获取缓存
    
    Args:
        key: 缓存键
    
    Returns:
        缓存的值，如果不存在或出错则返回 None
    """
    redis = await get_redis_client()
    if not redis:
        return None
    
    try:
        cached = await redis.get(f"{CACHE_PREFIX}{key}")
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.debug(f"获取缓存失败: {e}")
    return None


async def set_cached(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    设置缓存
    
    Args:
        key: 缓存键
        value: 要缓存的值
        ttl: 过期时间（秒），默认 5 分钟
    
    Returns:
        bool: 是否设置成功
    """
    redis = await get_redis_client()
    if not redis:
        return False
    
    try:
        await redis.setex(
            f"{CACHE_PREFIX}{key}",
            ttl,
            json.dumps(value, default=str)
        )
        return True
    except Exception as e:
        logger.debug(f"设置缓存失败: {e}")
        return False


async def invalidate_cache(pattern: str) -> int:
    """
    清除匹配模式的缓存
    
    Args:
        pattern: 缓存键模式（支持通配符）
    
    Returns:
        int: 清除的缓存数量
    """
    redis = await get_redis_client()
    if not redis:
        return 0
    
    try:
        keys = await redis.keys(f"{CACHE_PREFIX}{pattern}*")
        if keys:
            return await redis.delete(*keys)
    except Exception as e:
        logger.warning(f"清除缓存失败: {e}")
    return 0


def cache_query(ttl: int = DEFAULT_TTL, key_prefix: str = ""):
    """
    查询缓存装饰器
    
    Args:
        ttl: 缓存过期时间（秒）
        key_prefix: 缓存键前缀
    
    Usage:
        @cache_query(ttl=60, key_prefix="dashboard")
        async def get_dashboard_stats(period: str):
            # 查询逻辑
            return stats
    """
    def decorator(func: Callable) -> Callable:
        """将异步查询函数包装为带 Redis 缓存的版本。"""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """执行缓存读 → 未命中则调用原函数 → 写回缓存。"""
            # ---------- 生成缓存键 ----------
            cache_key = generate_cache_key(
                key_prefix or func.__name__,
                *args,
                **kwargs
            )
            
            # 尝试从缓存获取
            cached = await get_cached(cache_key)
            if cached is not None:
                logger.debug(f"缓存命中: {func.__name__}")
                return cached
            
            # 执行查询
            result = await func(*args, **kwargs)
            
            # 缓存结果（只缓存成功的结果）
            if result is not None:
                await set_cached(cache_key, result, ttl)
                logger.debug(f"缓存设置: {func.__name__}, TTL={ttl}s")
            
            return result
        return wrapper
    return decorator


async def clear_all_cache() -> int:
    """
    清除所有查询缓存
    
    Returns:
        int: 清除的缓存数量
    """
    return await invalidate_cache("")


async def get_or_set_cache(
    cache_key: str,
    fetch_func: Callable,
    ttl: int = DEFAULT_TTL,
    *args,
    **kwargs
) -> Any:
    """
    获取缓存，如果不存在则执行函数并缓存结果
    
    这是一个辅助函数，用于简化常见的缓存使用模式：
    1. 尝试从缓存获取
    2. 如果缓存不存在，执行 fetch_func 获取数据
    3. 将结果缓存起来
    
    Args:
        cache_key: 缓存键（已生成的完整键）
        fetch_func: 获取数据的异步函数（如果缓存不存在时调用）
        ttl: 缓存过期时间（秒），默认 5 分钟
        *args: 传递给 fetch_func 的位置参数
        **kwargs: 传递给 fetch_func 的关键字参数
    
    Returns:
        缓存的值或 fetch_func 的返回值
    
    Example:
        # 在端点中使用
        cache_key = generate_cache_key("user_stats")
        stats = await get_or_set_cache(
            cache_key,
            lambda: fetch_user_stats(db),
            ttl=300
        )
    """
    # 尝试从缓存获取
    cached = await get_cached(cache_key)
    if cached is not None:
        logger.debug(f"缓存命中: {cache_key[:20]}...")
        return cached
    
    # 缓存不存在，执行函数获取数据
    logger.debug(f"缓存未命中，执行查询: {cache_key[:20]}...")
    result = await fetch_func(*args, **kwargs)
    
    # 缓存结果（只缓存非 None 的结果）
    if result is not None:
        await set_cached(cache_key, result, ttl)
        logger.debug(f"缓存已设置: {cache_key[:20]}..., TTL={ttl}s")
    
    return result
