"""
缓存兼容层
保持与旧cache.py的兼容性，同时使用新的缓存抽象层
"""
import json
import hashlib
from typing import Any
from app.core.infrastructure.cache import get_cache_backend
import logging

logger = logging.getLogger(__name__)

# 兼容旧接口
async def get_cached(key: str):
    """兼容旧接口：获取缓存"""
    cache = await get_cache_backend()
    return await cache.get(key)

async def set_cached(key: str, value: Any, ttl: int = 300):
    """兼容旧接口：设置缓存"""
    cache = await get_cache_backend()
    return await cache.set(key, value, ttl=ttl)

def generate_cache_key(*args, **kwargs) -> str:
    """兼容旧接口：生成缓存键"""
    key_str = json.dumps(
        {"args": args, "kwargs": kwargs},
        sort_keys=True,
        default=str
    )
    return hashlib.md5(key_str.encode()).hexdigest()

