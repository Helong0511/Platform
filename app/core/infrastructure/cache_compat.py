"""
缓存兼容适配层。

职责：对外保持与旧 ``app.core.cache`` 相同的 get/set/invalidate 签名，
内部走基础设施层（Redis + 内存降级）并记录命中率指标。

在系统中的位置：业务模块逐步从 ``app.core.cache`` 迁移至本模块。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from functools import wraps
from typing import Any, Awaitable, Callable, Dict, Optional

from app.core.infrastructure.cache import get_cache_backend
from app.core.infrastructure.cache_metrics import get_metrics_collector

logger = logging.getLogger(__name__)

CACHE_PREFIX = "query_cache:"
DEFAULT_TTL = 300

# 进程内单飞：同 key 并发未命中只跑一次 factory，其余 await 同一 Future
_inflight_futures: Dict[str, asyncio.Future] = {}
_inflight_lock: Optional[asyncio.Lock] = None


def _get_inflight_lock() -> asyncio.Lock:
    global _inflight_lock
    if _inflight_lock is None:
        _inflight_lock = asyncio.Lock()
    return _inflight_lock


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


async def get_or_set_single_flight(
    cache_key: str,
    factory: Callable[[], Awaitable[Any]],
    *,
    ttl: int = DEFAULT_TTL,
    key_prefix: str = "query_cache",
    is_valid: Optional[Callable[[Any], bool]] = None,
    wait_timeout: float = 25.0,
    poll_interval: float = 0.05,
) -> Any:
    """
    读缓存；未命中时进程内单飞计算并写回，避免同 key 并发击穿。

    - 同进程：并发未命中共享一个 Future，只执行一次 factory
    - 跨 Worker：拿不到进程内 Future 时，用 Redis 锁；等锁方轮询缓存，
      超时仍未命中则自行计算（降级，保证有结果）

    Args:
        cache_key: 与 ``legacy_get_cached`` / ``legacy_set_cached`` 相同的业务键
        factory: 无参异步工厂，返回可缓存的完整载荷
        is_valid: 可选；判定缓存值是否可用（例如缺字段的旧值视为未命中）
        wait_timeout: 跟随者等待缓存填好的最长时间（秒）
    """

    def _ok(value: Any) -> bool:
        if value is None:
            return False
        if is_valid is None:
            return True
        try:
            return bool(is_valid(value))
        except Exception:
            return False

    cached = await legacy_get_cached(cache_key, key_prefix=key_prefix)
    if _ok(cached):
        return cached

    flight_key = _legacy_storage_key(cache_key)
    lock = _get_inflight_lock()
    leader_future: Optional[asyncio.Future] = None
    is_leader = False

    async with lock:
        existing = _inflight_futures.get(flight_key)
        if existing is not None and not existing.done():
            waiter = existing
        else:
            leader_future = asyncio.get_running_loop().create_future()
            _inflight_futures[flight_key] = leader_future
            is_leader = True
            waiter = None

    if not is_leader and waiter is not None:
        try:
            return await asyncio.wait_for(asyncio.shield(waiter), timeout=wait_timeout)
        except Exception:
            # 领导者失败或超时：再读一次缓存，仍无则自行计算
            cached = await legacy_get_cached(cache_key, key_prefix=key_prefix)
            if _ok(cached):
                return cached
            logger.warning(
                "缓存单飞跟随者降级自行计算: key=%s...",
                cache_key[:48],
            )
            result = await factory()
            if result is not None:
                await legacy_set_cached(
                    cache_key, result, ttl=ttl, key_prefix=key_prefix
                )
            return result

    # 领导者：优先尝试跨 Worker 锁，减少多进程同时打库
    acquired_lock = False
    dist_lock = None
    try:
        try:
            from app.core.infrastructure.cache_advanced import DistributedLock

            dist_lock = DistributedLock(f"sf:{flight_key}", timeout=int(max(5, wait_timeout)))
            acquired_lock = await dist_lock.acquire()
        except Exception as e:
            logger.debug("缓存单飞分布式锁不可用，仅进程内合并: %s", e)
            acquired_lock = True  # 无 Redis 锁时本进程仍作为计算方

        if not acquired_lock:
            # 其他 Worker 正在填充：轮询缓存
            deadline = time.monotonic() + wait_timeout
            while time.monotonic() < deadline:
                await asyncio.sleep(poll_interval)
                cached = await legacy_get_cached(cache_key, key_prefix=key_prefix)
                if _ok(cached):
                    if leader_future is not None and not leader_future.done():
                        leader_future.set_result(cached)
                    return cached
            logger.warning(
                "缓存单飞跨进程等待超时，降级自行计算: key=%s...",
                cache_key[:48],
            )

        # 双重检查
        cached = await legacy_get_cached(cache_key, key_prefix=key_prefix)
        if _ok(cached):
            if leader_future is not None and not leader_future.done():
                leader_future.set_result(cached)
            return cached

        result = await factory()
        if result is not None:
            await legacy_set_cached(cache_key, result, ttl=ttl, key_prefix=key_prefix)
        if leader_future is not None and not leader_future.done():
            leader_future.set_result(result)
        return result
    except Exception as e:
        if leader_future is not None and not leader_future.done():
            leader_future.set_exception(e)
        raise
    finally:
        if dist_lock is not None and acquired_lock:
            try:
                await dist_lock.release()
            except Exception:
                pass
        async with lock:
            if _inflight_futures.get(flight_key) is leader_future:
                _inflight_futures.pop(flight_key, None)
