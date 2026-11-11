"""
高级缓存防护策略模块。

职责：空值标记防穿透、互斥锁防击穿、随机 TTL 防雪崩，包装 ``get_cache_backend`` 读写。

在系统中的位置：热点配置/字典类数据可选用本模块的 ``cache_with_protection`` 等 API。
"""
import random
import secrets
import asyncio
import logging
from typing import Optional, Any, Callable, TypeVar
from contextlib import asynccontextmanager

from app.core.infrastructure.cache import get_cache_backend

logger = logging.getLogger(__name__)

# 类型变量
T = TypeVar('T')

# 特殊标记：表示"确实为空"（用于缓存穿透保护）
class NoneMarker:
    """None 值标记（区分缓存未命中和确实为空）"""
    _instance = None
    
    def __new__(cls):
        """单例：全局共用一个 NONE_MARKER，表示「缓存命中且值为空」。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __repr__(self):
        """调试输出固定标记名，便于日志区分 None 与未命中。"""
        return "<CACHE_NONE_MARKER>"
    
    def __bool__(self):
        """布尔上下文视为 False，但须用 ``is NONE_MARKER`` 与真 None 区分。"""
        return False  # 布尔值为 False，但可以用 is 判断

NONE_MARKER = NoneMarker()


async def get_with_none_cache(
    key: str,
    factory: Callable,
    none_ttl: int = 60,
    normal_ttl: int = 300
) -> Any:
    """
    带缓存穿透保护的获取方法
    
    如果查询结果为 None，也会缓存（带短 TTL），防止缓存穿透
    
    Args:
        key: 缓存键
        factory: 数据工厂函数（异步），当缓存未命中时调用
        none_ttl: None 值的 TTL（秒），默认 60 秒
        normal_ttl: 正常值的 TTL（秒），默认 300 秒
    
    Returns:
        数据或 None
    
    Example:
        user = await get_with_none_cache(
            f"user:{user_id}",
            lambda: get_user_from_db(user_id),
            none_ttl=60,
            normal_ttl=300
        )
    """
    cache = await get_cache_backend()
    
    # 尝试从缓存获取
    cached_value = await cache.get(key)
    
    # 检查是否是 None 标记
    if cached_value is not None:
        if isinstance(cached_value, dict) and cached_value.get('__none_marker__'):
            logger.debug(f"缓存命中（None 标记）: {key}")
            return None
        logger.debug(f"缓存命中：{key}")
        return cached_value
    
    # 缓存未命中，执行工厂函数
    logger.debug(f"缓存未命中：{key}，执行工厂函数")
    try:
        result = await factory()
    except Exception as e:
        logger.error(f"工厂函数执行失败：key={key}, error={e}", exc_info=True)
        raise
    
    # 写入缓存
    if result is None:
        # 缓存 None 标记（短 TTL）
        await cache.set(key, {'__none_marker__': True}, ttl=none_ttl)
        logger.debug(f"已缓存 None 标记：{key}, TTL={none_ttl}s")
    else:
        # 缓存正常值（带随机 TTL 偏移，防雪崩）
        ttl_with_jitter = normal_ttl + random.randint(-30, 30)
        await cache.set(key, result, ttl=ttl_with_jitter)
        logger.debug(f"已缓存数据：{key}, TTL={ttl_with_jitter}s")
    
    return result


def add_ttl_jitter(base_ttl: int, jitter_range: int = 300) -> int:
    """
    添加随机 TTL 偏移（防止缓存雪崩）

    Args:
        base_ttl: 基础 TTL
        jitter_range: 正向随机上限（秒），默认 +[1, 300]

    Returns:
        带随机偏移的 TTL
    """
    jitter = random.randint(1, max(1, jitter_range))
    return max(1, base_ttl + jitter)


async def set_with_jitter(
    key: str,
    value: Any,
    base_ttl: int,
    jitter_range: int = 30
) -> bool:
    """
    设置缓存（带随机 TTL 偏移）
    
    Args:
        key: 缓存键
        value: 缓存值
        base_ttl: 基础 TTL（秒）
        jitter_range: 随机范围（±秒）
    
    Returns:
        是否成功
    """
    ttl = add_ttl_jitter(base_ttl, jitter_range)
    cache = await get_cache_backend()
    return await cache.set(key, value, ttl=ttl)


# Redis 分布式锁实现（用于缓存击穿保护）
class DistributedLock:
    """
    分布式锁（基于 Redis）
    
    用于防止缓存击穿（热点 Key 过期时大量并发请求）
    """
    
    # 比较并删除必须在 Redis 内原子完成，避免 GET 与 DELETE 之间锁过期后误删新持有者的锁。
    _RELEASE_LUA = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
        return redis.call('DEL', KEYS[1])
    end
    return 0
    """

    def __init__(self, key: str, timeout: int = 10):
        """
        Args:
            key: 锁键
            timeout: 锁超时时间（秒），防止死锁
        """
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.lock_value = secrets.token_urlsafe(32)
    
    async def acquire(self) -> bool:
        """
        尝试获取锁
        
        Returns:
            是否成功获取
        """
        cache = await get_cache_backend()
        
        # 尝试设置锁（NX 表示仅当键不存在时设置）
        # 使用 Redis 的 SET NX EX 命令实现原子操作
        if hasattr(cache, 'redis') and cache.redis:
            try:
                # 使用 Redis 的 SET NX EX 命令
                result = await cache.redis.set(
                    self.key,
                    self.lock_value,
                    nx=True,
                    ex=self.timeout
                )
                if result:
                    logger.debug(f"获取分布式锁成功：{self.key}")
                    return True
                else:
                    logger.debug(f"获取分布式锁失败（已被占用）：{self.key}")
                    return False
            except Exception as e:
                logger.error(f"获取分布式锁失败：{e}", exc_info=True)
                return False
        else:
            # 内存缓存降级（不支持分布式锁）
            logger.warning(f"内存缓存不支持分布式锁，跳过：{self.key}")
            return True
    
    async def release(self) -> bool:
        """
        释放锁
        
        Returns:
            是否成功释放
        """
        cache = await get_cache_backend()
        
        if hasattr(cache, 'redis') and cache.redis:
            try:
                # Lua 将 owner 校验与删除合并为单条原子操作，避免锁过期/重获期间误删新锁。
                released = await cache.redis.eval(
                    self._RELEASE_LUA,
                    1,
                    self.key,
                    self.lock_value,
                )
                if int(released or 0) == 1:
                    logger.debug(f"释放分布式锁成功：{self.key}")
                    return True
                logger.debug(f"锁已过期或不属于当前实例，跳过释放：{self.key}")
                return False
            except Exception as e:
                logger.error(f"释放分布式锁失败：{e}", exc_info=True)
                return False
        else:
            # 内存缓存降级
            logger.warning(f"内存缓存不支持分布式锁释放：{self.key}")
            return True


@asynccontextmanager
async def distributed_lock(key: str, timeout: int = 10, retry: bool = False, retry_delay: float = 0.1):
    """
    分布式锁上下文管理器
    
    Args:
        key: 锁键
        timeout: 锁超时时间（秒）
        retry: 是否重试（如果获取失败）
        retry_delay: 重试间隔（秒）
    
    Yields:
        是否成功获取锁
    
    Example:
        async with distributed_lock(f"user:{user_id}") as acquired:
            if acquired:
                # 执行临界区代码
                user = await get_user_from_db(user_id)
                await cache.set(f"user:{user_id}", user)
            else:
                # 锁被占用，从缓存重试
                user = await cache.get(f"user:{user_id}")
    """
    lock = DistributedLock(key, timeout)
    acquired = await lock.acquire()
    
    if not acquired and retry:
        # 重试逻辑
        max_retries = int(timeout / retry_delay)
        for i in range(max_retries):
            await asyncio.sleep(retry_delay)
            acquired = await lock.acquire()
            if acquired:
                break
        
        if not acquired:
            logger.warning(f"获取分布式锁超时：{key}")
    
    try:
        yield acquired
    finally:
        if acquired:
            await lock.release()


async def get_with_lock_protection(
    key: str,
    factory: Callable,
    ttl: int = 300,
    lock_timeout: int = 10
) -> Any:
    """
    带分布式锁保护的缓存获取（防止缓存击穿）
    
    Args:
        key: 缓存键
        factory: 数据工厂函数（异步）
        ttl: 缓存 TTL（秒）
        lock_timeout: 锁超时时间（秒）
    
    Returns:
        数据
    
    Example:
        user = await get_with_lock_protection(
            f"user:{user_id}",
            lambda: get_user_from_db(user_id),
            ttl=300,
            lock_timeout=10
        )
    """
    cache = await get_cache_backend()
    
    # 尝试从缓存获取
    cached_value = await cache.get(key)
    if cached_value is not None:
        if isinstance(cached_value, dict) and cached_value.get('__none_marker__'):
            return None
        return cached_value
    
    # 缓存未命中，尝试获取锁
    async with distributed_lock(key, timeout=lock_timeout, retry=True) as acquired:
        if acquired:
            # 双重检查（避免其他进程已经填充缓存）
            cached_value = await cache.get(key)
            if cached_value is not None:
                if isinstance(cached_value, dict) and cached_value.get('__none_marker__'):
                    return None
                return cached_value
            
            # 执行工厂函数
            logger.info(f"缓存未命中，执行工厂函数（持有锁）：{key}")
            try:
                result = await factory()
            except Exception as e:
                logger.error(f"工厂函数执行失败：key={key}, error={e}", exc_info=True)
                raise
            
            # 写入缓存
            if result is None:
                await cache.set(key, {'__none_marker__': True}, ttl=60)
            else:
                ttl_with_jitter = add_ttl_jitter(ttl)
                await cache.set(key, result, ttl=ttl_with_jitter)
            
            return result
        else:
            # 锁获取失败，短暂等待后重试
            logger.warning(f"获取锁失败，等待后重试：{key}")
            await asyncio.sleep(0.1)
            
            # 重试获取缓存
            cached_value = await cache.get(key)
            if cached_value is not None:
                if isinstance(cached_value, dict) and cached_value.get('__none_marker__'):
                    return None
                return cached_value
            
            # 仍然失败，抛出异常或返回 None
            logger.error(f"缓存击穿保护失败：{key}")
            return None
