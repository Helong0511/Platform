"""
Redis Cap 计数器实现
用于高性能的 Cap 检查和计数

Key 结构:
cpl:cap:daily:{offer_id}:{date_str} -> int
cpl:cap:total:{offer_id} -> int
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Key 前缀
KEY_PREFIX = "cpl:cap"
DEFAULT_EXPIRE_SECONDS = 48 * 3600  # 48小时过期，保留足够的时间窗口


def get_daily_cap_key(offer_id: int, date: datetime, publisher_id: Optional[int] = None) -> str:
    """生成每日 Cap 的 Key"""
    date_str = date.strftime("%Y-%m-%d")
    key = f"{KEY_PREFIX}:daily:{offer_id}:{date_str}"
    if publisher_id:
        key += f":pub:{publisher_id}"
    return key


def get_total_cap_key(offer_id: int, publisher_id: Optional[int] = None) -> str:
    """生成总 Cap 的 Key"""
    key = f"{KEY_PREFIX}:total:{offer_id}"
    if publisher_id:
        key += f":pub:{publisher_id}"
    return key


class RedisCapManager:
    """Redis Cap 管理器"""
    
    # Lua 脚本：原子递增并设置过期时间
    # KEYS[1]: cap_key
    # ARGV[1]: expire_seconds
    # ARGV[2]: initial_value (可选，用于冷启动同步)
    _INCR_LUA = """
    local current = redis.call('GET', KEYS[1])
    if not current then
        local val = 1
        if ARGV[2] and ARGV[2] ~= "" then
            val = tonumber(ARGV[2]) + 1
        end
        redis.call('SET', KEYS[1], val)
        redis.call('EXPIRE', KEYS[1], ARGV[1])
        return val
    else
        return redis.call('INCR', KEYS[1])
    end
    """

    @staticmethod
    async def check_and_increment_daily(
        offer_id: int, 
        limit: int, 
        publisher_id: Optional[int] = None,
        initial_value: Optional[int] = None
    ) -> bool:
        """
        检查并增加每日计数 (原子操作)
        
        Args:
            offer_id: Offer ID
            limit: 限制数量
            publisher_id: 渠道 ID (可选)
            initial_value: 如果 Key 不存在，使用的初始值 (通常来自 DB)
            
        Returns:
            bool: True=允许通过(未超量), False=已超量
        """
        redis = await get_redis_client()
        if not redis:
            logger.warning("Redis不可用，Cap检查跳过 (Fail Open)")
            return True
            
        now = datetime.now(timezone.utc)
        key = get_daily_cap_key(offer_id, now, publisher_id)
        
        try:
            # 执行 Lua 脚本实现原子操作
            # initial_value 如果为 None，传空字符串给 Lua
            init_val = str(initial_value) if initial_value is not None else ""
            current = await redis.eval(
                RedisCapManager._INCR_LUA, 1, key, DEFAULT_EXPIRE_SECONDS, init_val
            )
            
            # 检查是否超量
            if current > limit:
                return False
                
            return True
        except Exception as e:
            logger.error(f"Redis Lua操作失败: {e}", exc_info=True)
            return True  # Fail Open

    @staticmethod
    async def check_and_increment_total(
        offer_id: int, 
        limit: int, 
        publisher_id: Optional[int] = None,
        initial_value: Optional[int] = None
    ) -> bool:
        """
        检查并增加总计数
        """
        redis = await get_redis_client()
        if not redis:
            return True
            
        key = get_total_cap_key(offer_id, publisher_id)
        
        try:
            init_val = str(initial_value) if initial_value is not None else ""
            # 总 Cap 过期时间设长一点（比如 30 天）或者不设，这里设 30 天作为兜底
            current = await redis.eval(
                RedisCapManager._INCR_LUA, 1, key, 30 * 24 * 3600, init_val
            )
            
            if current > limit:
                return False
            return True
        except Exception as e:
            logger.error(f"Redis Lua操作失败: {e}", exc_info=True)
            return True
            
    @staticmethod
    async def decrement_daily(
        offer_id: int, 
        publisher_id: Optional[int] = None
    ):
        """
        减少每日计数 (用于回滚)
        """
        redis = await get_redis_client()
        if not redis: return
        
        now = datetime.now(timezone.utc)
        key = get_daily_cap_key(offer_id, now, publisher_id)
        try:
            val = await redis.decr(key)
            # 避免减成负数 (虽然通常不会发生)
            if val < 0:
                await redis.set(key, 0)
        except Exception as e:
            logger.error(f"Redis回滚失败: {e}")

    @staticmethod
    async def decrement_total(
        offer_id: int, 
        publisher_id: Optional[int] = None
    ):
        """减少总计数 (用于回滚)"""
        redis = await get_redis_client()
        if not redis: return
        
        key = get_total_cap_key(offer_id, publisher_id)
        try:
            val = await redis.decr(key)
            # 避免减成负数
            if val < 0:
                await redis.set(key, 0)
        except Exception as e:
            logger.error(f"Redis回滚失败: {e}")
    
    @staticmethod
    async def clear_daily_cap_keys(offer_id: Optional[int] = None, publisher_id: Optional[int] = None):
        """
        清理每日Cap的Redis key（用于定时任务重置）
        
        Args:
            offer_id: 如果指定，只清理该Offer的key；如果为None，清理所有
            publisher_id: 如果指定，只清理该Publisher的key；如果为None，清理所有
        """
        redis = await get_redis_client()
        if not redis:
            logger.warning("Redis不可用，跳过清理每日Cap key")
            return
        
        try:
            # 构建匹配模式
            if offer_id:
                pattern = f"{KEY_PREFIX}:daily:{offer_id}:*"
            else:
                pattern = f"{KEY_PREFIX}:daily:*"
            
            if publisher_id:
                pattern += f":pub:{publisher_id}"
            
            # 使用SCAN迭代所有匹配的key（避免阻塞）
            deleted_count = 0
            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                if keys:
                    # 批量删除
                    deleted = await redis.delete(*keys)
                    deleted_count += deleted
                if cursor == 0:
                    break
            
            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个每日Cap Redis key (pattern={pattern})")
        except Exception as e:
            logger.error(f"清理每日Cap Redis key失败: {e}", exc_info=True)
