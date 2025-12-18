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
    
    @staticmethod
    async def check_and_increment_daily(
        offer_id: int, 
        limit: int, 
        publisher_id: Optional[int] = None
    ) -> bool:
        """
        检查并增加每日计数 (原子操作)
        
        Args:
            offer_id: Offer ID
            limit: 限制数量
            publisher_id: 渠道 ID (可选)
            
        Returns:
            bool: True=允许通过(未超量), False=已超量
        """
        redis = await get_redis_client()
        if not redis:
            # 降级策略：如果 Redis 不可用，返回 True (允许通过) 或抛出异常
            # 这里选择谨慎策略，记录日志并允许通过（依赖后续 DB 检查或由业务决定）
            logger.warning("Redis不可用，Cap检查跳过 (Fail Open)")
            return True
            
        now = datetime.now(timezone.utc)
        key = get_daily_cap_key(offer_id, now, publisher_id)
        
        try:
            # 原子递增
            # 1. INCR key
            # 2. 如果是新 key (value=1)，设置过期时间
            current = await redis.incr(key)
            
            if current == 1:
                await redis.expire(key, DEFAULT_EXPIRE_SECONDS)
                
            # 检查是否超量
            if current > limit:
                # 即使超量也保留计数，以便统计超量程度
                # 但为了防止无限增长，可以考虑不再递增? 
                # 不，INCR 已经执行了。如果不想污染计数，可以使用 Lua 脚本做到 "check and incr"
                # 但简单的 INCR 即使超量也无所谓，只需返回 False
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Redis操作失败: {e}", exc_info=True)
            return True  # Fail Open

    @staticmethod
    async def check_and_increment_total(
        offer_id: int, 
        limit: int, 
        publisher_id: Optional[int] = None
    ) -> bool:
        """
        检查并增加总计数
        """
        redis = await get_redis_client()
        if not redis:
            return True
            
        key = get_total_cap_key(offer_id, publisher_id)
        
        try:
            current = await redis.incr(key)
            # 总 Cap 的 key 不设过期时间，或设得很长
            
            if current > limit:
                return False
            return True
        except Exception as e:
            logger.error(f"Redis操作失败: {e}", exc_info=True)
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
            await redis.decr(key)
        except Exception as e:
            logger.error(f"Redis回滚失败: {e}")
