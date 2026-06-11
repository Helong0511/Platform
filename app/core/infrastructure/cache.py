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
    """内存缓存后端实现（Redis不可用时的降级方案）"""
    
    def __init__(self):
        """初始化进程内字典缓存，键值附带可选过期时间戳。"""
        self._cache: Dict[str, tuple[Any, Optional[float]]] = {}
        self._time = time.time
    
    async def get(self, key: str) -> Optional[Any]:
        """从内存获取缓存值"""
        if key not in self._cache:
            return None
        
        value, expire_time = self._cache[key]
        
        # 检查是否过期
        if expire_time and self._time() > expire_time:
            del self._cache[key]
            return None
        
        return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置内存缓存值"""
        expire_time = None
        if ttl:
            expire_time = self._time() + ttl
        
        self._cache[key] = (value, expire_time)
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
        
        # 检查是否过期
        value, expire_time = self._cache[key]
        if expire_time and self._time() > expire_time:
            del self._cache[key]
            return False
        
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
    """缓存失效管理器"""
    
    @staticmethod
    async def invalidate_user_cache(user_id: int):
        """失效用户相关缓存"""
        cache = await get_cache_backend()
        patterns = [
            f"user:{user_id}",
            "user:list:*",
            "user_stats",
        ]
        for pattern in patterns:
            await cache.delete_pattern(pattern)
    
    @staticmethod
    async def invalidate_product_cache(product_id: int):
        """失效产品相关缓存"""
        cache = await get_cache_backend()
        patterns = [
            f"product:{product_id}",
            "product:list:*",
            "stats:*",
        ]
        for pattern in patterns:
            await cache.delete_pattern(pattern)
    
    @staticmethod
    async def invalidate_offer_cache(offer_id: int):
        """失效Offer相关缓存"""
        cache = await get_cache_backend()
        patterns = [
            f"offer:{offer_id}",
            "offer:list:*",
            "stats:*",
        ]
        for pattern in patterns:
            await cache.delete_pattern(pattern)

