"""
缓存兼容适配层。

职责：对外保持与旧 ``app.core.cache`` 相同的 get/set/invalidate 签名，
内部走基础设施层（Redis + 内存降级）并记录命中率指标。

在系统中的位置：业务模块逐步从 ``app.core.cache`` 迁移至本模块。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from functools import wraps
from typing import Any, Callable, Optional

from app.core.infrastructure.cache import get_cache_backend
from app.core.infrastructure.cache_metrics import get_metrics_collector

logger = logging.getLogger(__name__)

CACHE_PREFIX = "query_cache:"
DEFAULT_TTL = 300


def _legacy_storage_key(key: str) -> str:
    """旧层键名：自动补 ``query_cache:`` 前缀（已含则不再重复）。"""
    if key.startswith(CACHE_PREFIX):
        return key
    return f"{CACHE_PREFIX}{key}"


async def get_cached(key: str, key_prefix: str = "global") -> Optional[Any]:
    """
    获取缓存（带监控）。

    Args:
        key: 完整 Redis 键（调用 legacy_get_cached 时由内部加前缀）
        key_prefix: 指标分类前缀
    """
    start_time = time.time()
    cache = await get_cache_backend()
    metrics = get_metrics_collector()

    try:
        value = await cache.get(key)
        response_time_ms = (time.time() - start_time) * 1000

        if value is not None:
            logger.debug(
                "缓存命中：key=%s, response_time=%.2fms", key, response_time_ms
            )
            metrics.record_hit(key_prefix, response_time_ms)
        else:
            logger.debug(
                "缓存未命中：key=%s, response_time=%.2fms", key, response_time_ms
            )
            metrics.record_miss(key_prefix, response_time_ms)

        return value

    except Exception as e:
        metrics.record_error(key_prefix)
        logger.error("获取缓存失败：key=%s, error=%s", key, e, exc_info=True)
        return None


async def set_cached(
    key: str,
    value: Any,
    ttl: int = DEFAULT_TTL,
    key_prefix: str = "global",
) -> bool:
    """设置缓存（带监控）。"""
    start_time = time.time()
    cache = await get_cache_backend()
    metrics = get_metrics_collector()

    try:
        result = await cache.set(key, value, ttl=ttl)
        response_time_ms = (time.time() - start_time) * 1000
        logger.debug(
            "设置缓存成功：key=%s, ttl=%ss, response_time=%.2fms",
            key,
            ttl,
            response_time_ms,
        )
        return result

    except Exception as e:
        metrics.record_error(key_prefix)
        logger.error("设置缓存失败：key=%s, error=%s", key, e, exc_info=True)
        return False


async def legacy_get_cached(
    key: str,
    key_prefix: str = "query_cache",
) -> Optional[Any]:
    """旧 ``app.core.cache.get_cached`` 兼容：自动加 ``query_cache:`` 前缀。"""
    return await get_cached(_legacy_storage_key(key), key_prefix=key_prefix)


async def legacy_set_cached(
    key: str,
    value: Any,
    ttl: int = DEFAULT_TTL,
    key_prefix: str = "query_cache",
) -> bool:
    """旧 ``app.core.cache.set_cached`` 兼容：自动加 ``query_cache:`` 前缀。"""
    return await set_cached(
        _legacy_storage_key(key),
        value,
        ttl=ttl,
        key_prefix=key_prefix,
    )


async def invalidate_cache(pattern: str) -> int:
    """
    按模式清除旧层 ``query_cache:`` 命名空间下的缓存（使用 SCAN，非 KEYS）。
    """
    cache = await get_cache_backend()
    full_pattern = f"{CACHE_PREFIX}{pattern}*"
    try:
        deleted = await cache.delete_pattern(full_pattern)
        if deleted:
            logger.debug("清除缓存：pattern=%s, count=%d", full_pattern, deleted)
        return deleted
    except Exception as e:
        logger.warning("清除缓存失败：pattern=%s, error=%s", full_pattern, e)
        return 0


async def clear_all_cache() -> int:
    """清除所有 ``query_cache:`` 前缀的查询缓存。"""
    return await invalidate_cache("")


def generate_cache_key(*args, **kwargs) -> str:
    """根据参数生成 MD5 哈希缓存键（不含 ``query_cache:`` 前缀）。"""
    key_str = json.dumps(
        {"args": args, "kwargs": kwargs},
        sort_keys=True,
        default=str,
    )
    return hashlib.md5(key_str.encode()).hexdigest()


def cache_query(ttl: int = DEFAULT_TTL, key_prefix: str = ""):
    """查询缓存装饰器（旧 API 兼容）。"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = generate_cache_key(
                key_prefix or func.__name__,
                *args,
                **kwargs,
            )
            metric_prefix = key_prefix or func.__name__

            cached = await legacy_get_cached(cache_key, key_prefix=metric_prefix)
            if cached is not None:
                logger.debug("缓存命中: %s", func.__name__)
                return cached

            result = await func(*args, **kwargs)

            if result is not None:
                await legacy_set_cached(
                    cache_key,
                    result,
                    ttl=ttl,
                    key_prefix=metric_prefix,
                )
                logger.debug("缓存设置: %s, TTL=%ss", func.__name__, ttl)

            return result

        return wrapper

    return decorator


async def get_or_set_cache(
    cache_key: str,
    fetch_func: Callable,
    ttl: int = DEFAULT_TTL,
    key_prefix: str = "query_cache",
    *args,
    **kwargs,
) -> Any:
    """读缓存；未命中则执行 fetch_func 并写回。"""
    cached = await legacy_get_cached(cache_key, key_prefix=key_prefix)
    if cached is not None:
        logger.debug("缓存命中: %s...", cache_key[:20])
        return cached

    logger.debug("缓存未命中，执行查询: %s...", cache_key[:20])
    result = await fetch_func(*args, **kwargs)

    if result is not None:
        await legacy_set_cached(cache_key, result, ttl=ttl, key_prefix=key_prefix)
        logger.debug("缓存已设置: %s..., TTL=%ss", cache_key[:20], ttl)

    return result
