"""
缓存抽象层
提供统一的缓存接口，支持多种缓存后端
"""
import asyncio
import json
import time
import re
import hashlib
import logging
from collections import OrderedDict
from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Any, Dict
from functools import wraps
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    """Redis 缓存 JSON 序列化：处理 Decimal、日期等常见不可序列化类型。"""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


class CacheBackend(ABC):
    """缓存后端抽象接口"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        pass
    
    @abstractmethod
    async def delete_pattern(self, pattern: str) -> int:
        """按模式删除缓存（返回删除数量）"""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        pass


class RedisCacheBackend(CacheBackend):
    """Redis缓存后端实现"""
    
    def __init__(self, redis_client):
        """
        Args:
            redis_client: 已连接的 aioredis 客户端实例；为 None 时所有操作降级为无缓存
        """
        self.redis = redis_client
    
    async def get(self, key: str) -> Optional[Any]:
        """从Redis获取缓存值"""
        if not self.redis:
            return None
        
        try:
            value = await self.redis.get(key)
            if value is None:
                return None
            # 尝试JSON解析
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # 如果不是JSON，直接返回字符串
                return value
        except Exception as e:
            logger.warning(f"Redis获取缓存失败: key={key}, error={e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置Redis缓存值"""
        if not self.redis:
            return False
        
        try:
            # 序列化值
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(
                    value, ensure_ascii=False, default=_json_default
                )
            else:
                serialized_value = str(value)
            
            if ttl:
                await self.redis.setex(key, ttl, serialized_value)
            else:
                await self.redis.set(key, serialized_value)
            
            return True
        except Exception as e:
            logger.warning(f"Redis设置缓存失败: key={key}, error={e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """删除Redis缓存"""
        if not self.redis:
            return False
        
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis删除缓存失败: key={key}, error={e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """按模式删除Redis缓存"""
        if not self.redis:
            return 0
        
        try:
            # Redis SCAN命令查找匹配的键
            deleted_count = 0
            cursor = 0
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted_count += await self.redis.delete(*keys)
                if cursor == 0:
                    break
            
            return deleted_count
        except Exception as e:
            logger.warning(f"Redis按模式删除缓存失败: pattern={pattern}, error={e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """检查Redis键是否存在"""
        if not self.redis:
            return False
        
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.warning(f"Redis检查键存在失败: key={key}, error={e}")
            return False


class MemoryCacheBackend(CacheBackend):
    """内存缓存后端实现（Redis不可用时的有界降级方案）。"""

    DEFAULT_MAX_ENTRIES = 10000

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        """初始化有界 LRU 缓存，避免 Redis 故障期间高基数键耗尽进程内存。"""
        self._cache: OrderedDict[str, tuple[Any, Optional[float]]] = OrderedDict()
        self._max_entries = max(1, int(max_entries))
        self._time = time.time

    async def get(self, key: str) -> Optional[Any]:
        """从内存获取缓存值，并更新 LRU 最近访问顺序。"""
        entry = self._cache.get(key)
        if entry is None:
            return None

        value, expire_time = entry
        if expire_time is not None and self._time() >= expire_time:
            self._cache.pop(key, None)
            return None

        self._cache.move_to_end(key)
        return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """写入缓存；达到容量上限时淘汰最久未访问项。"""
        expire_time = None
        if ttl:
            expire_time = self._time() + max(0, ttl)

        self._cache[key] = (value, expire_time)
        self._cache.move_to_end(key)

        # 先清除已过期的最旧条目，避免在缓存写入高峰期保留过期对象。
        now = self._time()
        expired_keys = [
            cache_key
            for cache_key, (_, expires_at) in self._cache.items()
            if expires_at is not None and now >= expires_at
        ]
        for cache_key in expired_keys:
            self._cache.pop(cache_key, None)

        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)
        return True
    
    async def delete(self, key: str) -> bool:
        """删除内存缓存"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """按模式删除内存缓存（简单实现）"""
        try:
            # 将glob模式转换为正则表达式
            regex = pattern.replace('*', '.*').replace('?', '.')
            pattern_re = re.compile(f'^{regex}$')
            
            deleted_keys = [key for key in self._cache.keys() if pattern_re.match(key)]
            for key in deleted_keys:
                del self._cache[key]
            
            return len(deleted_keys)
        except Exception as e:
            logger.warning(f"内存缓存按模式删除失败: pattern={pattern}, error={e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """检查内存键是否存在"""
        if key not in self._cache:
            return False
        
        # 检查是否过期，并更新 LRU 最近访问顺序。
        _, expire_time = self._cache[key]
        if expire_time is not None and self._time() >= expire_time:
            del self._cache[key]
            return False

        self._cache.move_to_end(key)
        return True


# 全局缓存后端实例（绑定创建时的事件循环）
_cache_backend: Optional[CacheBackend] = None
_cache_loop: Optional[asyncio.AbstractEventLoop] = None


async def get_cache_backend() -> CacheBackend:
    """获取缓存后端实例（单例模式）"""
    global _cache_backend, _cache_loop

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _cache_backend is not None and current_loop is not None:
        if _cache_loop is not current_loop or _cache_loop.is_closed():
            _cache_backend = None
            _cache_loop = None
    
    if _cache_backend is None:
        # 尝试使用Redis
        redis_client = await get_redis_client()
        if redis_client:
            _cache_backend = RedisCacheBackend(redis_client)
            logger.info("使用Redis作为缓存后端")
        else:
            # 降级到内存缓存
            _cache_backend = MemoryCacheBackend()
            logger.info("使用内存缓存作为缓存后端（Redis不可用）")

        if current_loop is not None:
            _cache_loop = current_loop
    
    return _cache_backend


def cached(key_pattern: str, ttl: int = 300):
    """
    缓存装饰器
    
    Args:
        key_pattern: 缓存键模式，支持格式化字符串（如 "user:{user_id}"）
        ttl: 缓存过期时间（秒），默认300秒
    
    Example:
        @cached("user:{user_id}", ttl=3600)
        async def get_user(user_id: int):
            # 函数逻辑
            pass
    """
    def decorator(func):
        """将异步函数包装为带基础设施层缓存的版本。"""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """读缓存 → 未命中执行原函数 → 写回缓存。"""
            # ---------- 生成缓存键 ----------
            try:
                cache_key = key_pattern.format(*args, **kwargs)
            except (KeyError, IndexError):
                # 如果格式化失败，使用函数名和参数
                key_str = f"{func.__name__}:{str(args)}:{str(kwargs)}"
                cache_key = f"cache:{hashlib.md5(key_str.encode()).hexdigest()}"
            
            # 尝试从缓存获取
            cache = await get_cache_backend()
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return cached_value
            
            # 执行函数
            logger.debug(f"缓存未命中: {cache_key}，执行函数")
            result = await func(*args, **kwargs)
            
            # 写入缓存
            await cache.set(cache_key, result, ttl=ttl)
            
            return result
        
        return wrapper
    return decorator


class CacheInvalidator:
    """缓存失效管理器（支持延迟双删）。"""

    @staticmethod
    async def _delete_patterns(patterns: list[str]) -> None:
        cache = await get_cache_backend()
        for pattern in patterns:
            await cache.delete_pattern(pattern)

    @staticmethod
    async def _delayed_double_delete(patterns: list[str], extra_coros=None) -> None:
        """先删一次，延迟后再删一次，降低并发回填脏缓存窗口。"""
        from app.core.config import settings

        delay = float(getattr(settings, "CACHE_DOUBLE_DELETE_DELAY_SECONDS", 1.0))

        async def _second_pass() -> None:
            try:
                await asyncio.sleep(max(0.1, delay))
                await CacheInvalidator._delete_patterns(patterns)
                if extra_coros:
                    for coro_factory in extra_coros:
                        try:
                            await coro_factory()
                        except Exception as exc:
                            logger.debug("延迟双删附加清理失败: %s", exc)
            except Exception as exc:
                logger.debug("延迟双删失败: %s", exc)

        asyncio.create_task(_second_pass())

    @staticmethod
    async def invalidate_user_cache(user_id: int):
        """失效用户相关缓存"""
        patterns = [
            f"user:{user_id}",
            "user:list:*",
            "user_stats",
        ]
        await CacheInvalidator._delete_patterns(patterns)
        await CacheInvalidator._delayed_double_delete(patterns)

    @staticmethod
    async def invalidate_product_cache(product_id: int):
        """失效产品相关缓存"""
        patterns = [
            f"product:{product_id}",
            "product:list:*",
            "stats:*",
        ]
        await CacheInvalidator._delete_patterns(patterns)
        await CacheInvalidator._delayed_double_delete(patterns)

    @staticmethod
    async def invalidate_offer_cache(offer_id: int):
        """失效Offer相关缓存（先删 + 延迟双删）"""
        from app.core.offer_cache import invalidate_offer_cache as invalidate_hot_offer_cache

        await invalidate_hot_offer_cache(offer_id)
        patterns = [
            f"offer:{offer_id}",
            "offer:list:*",
            "stats:*",
        ]
        await CacheInvalidator._delete_patterns(patterns)

        async def _hot_again():
            await invalidate_hot_offer_cache(offer_id)

        await CacheInvalidator._delayed_double_delete(patterns, extra_coros=[_hot_again])

    @staticmethod
    async def invalidate_advertiser_cache(advertiser_id: int):
        """失效广告主及依赖广告主数据的列表缓存"""
        patterns = [
            f"advertiser:{advertiser_id}",
            "advertiser:list:*",
            "offer:list:*",
            "stats:*",
        ]
        await CacheInvalidator._delete_patterns(patterns)
        await CacheInvalidator._delayed_double_delete(patterns)

