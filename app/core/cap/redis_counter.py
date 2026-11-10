"""
Redis Cap 计数器实现
用于高性能的 Cap 检查和计数

Key 结构:
cpl:cap:daily:{offer_id}:{date_str} -> int
cpl:cap:total:{offer_id} -> int
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.core.redis_client import get_redis_client
from app.core.config import settings
from app.core.utils import get_app_now_naive

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
    def _redis_unavailable_result() -> bool:
        """Redis 不可用时按 CAP_FAIL_OPEN 决定放行或拒绝。"""
        if settings.CAP_FAIL_OPEN:
            logger.warning("Redis不可用，Cap fail-open 放行")
            return True
        logger.error("Redis不可用，Cap fail-close 拒绝")
        return False

    @staticmethod
    def _lua_failure_result() -> bool:
        if settings.CAP_FAIL_OPEN:
            logger.warning("Redis Cap Lua 失败，fail-open 放行")
            return True
        logger.error("Redis Cap Lua 失败，fail-close 拒绝")
        return False
    
    # Lua：先判限再递增，超限返回 -1（不修改 key）
    # KEYS[1]: cap_key
    # ARGV[1]: expire_seconds
    # ARGV[2]: initial_value（冷启动，key 不存在时使用）
    # ARGV[3]: limit
    _RESERVE_LUA = """
    local limit = tonumber(ARGV[3])
    local current = redis.call('GET', KEYS[1])
    if not current then
        current = tonumber(ARGV[2]) or 0
    else
        current = tonumber(current)
    end
    if current >= limit then
        return -1
    end
    local new_val = current + 1
    redis.call('SET', KEYS[1], new_val)
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    return new_val
    """

    # Lua：原子回滚（decr 后若 <0 则归零，避免并发 set 覆盖丢失计数）
    # KEYS[1]: cap_key
    # 返回: 回滚后的最终值
    _DECREMENT_LUA = """
    -- 不对不存在的 key 执行 DECR，避免创建没有 TTL 的负数 key。
    local current = redis.call('GET', KEYS[1])
    if not current then
        return 0
    end
    local val = redis.call('DECR', KEYS[1])
    if val < 0 then
        -- INCR 恢复到 0，保留原 TTL；SET 会清除 TTL。
        redis.call('INCR', KEYS[1])
        return 0
    end
    return val
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
            return RedisCapManager._redis_unavailable_result()
            
        now = get_app_now_naive()
        key = get_daily_cap_key(offer_id, now, publisher_id)
        
        try:
            init_val = str(initial_value) if initial_value is not None else "0"
            current = await redis.eval(
                RedisCapManager._RESERVE_LUA,
                1,
                key,
                DEFAULT_EXPIRE_SECONDS,
                init_val,
                str(limit),
            )
            if int(current) < 0:
                return False
            return True
        except Exception as e:
            logger.error(f"Redis Lua操作失败: {e}", exc_info=True)
            return RedisCapManager._lua_failure_result()

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
            return RedisCapManager._redis_unavailable_result()
            
        key = get_total_cap_key(offer_id, publisher_id)
        
        try:
            init_val = str(initial_value) if initial_value is not None else "0"
            current = await redis.eval(
                RedisCapManager._RESERVE_LUA,
                1,
                key,
                30 * 24 * 3600,
                init_val,
                str(limit),
            )
            if int(current) < 0:
                return False
            return True
        except Exception as e:
            logger.error(f"Redis Lua操作失败: {e}", exc_info=True)
            return RedisCapManager._lua_failure_result()
            
    @staticmethod
    async def decrement_daily(
        offer_id: int,
        publisher_id: Optional[int] = None
    ) -> int:
        """
        减少每日计数 (用于回滚，原子操作)

        Returns:
            int: 回滚后的最终计数值；Redis 不可用或异常返回 -1
        """
        redis = await get_redis_client()
        if not redis:
            return -1

        now = get_app_now_naive()
        key = get_daily_cap_key(offer_id, now, publisher_id)
        try:
            # 使用 Lua 脚本原子化 decr + 负数归零，避免 TOCTOU 竞态
            # （decr 后到 set(0) 之间若有 incr 会丢失计数或导致配额虚增）
            val = await redis.eval(RedisCapManager._DECREMENT_LUA, 1, key)
            return int(val)
        except Exception as e:
            logger.error(f"Redis回滚失败: {e}", exc_info=True)
            return -1

    @staticmethod
    async def decrement_total(
        offer_id: int,
        publisher_id: Optional[int] = None
    ) -> int:
        """
        减少总计数 (用于回滚，原子操作)

        Returns:
            int: 回滚后的最终计数值；Redis 不可用或异常返回 -1
        """
        redis = await get_redis_client()
        if not redis:
            return -1

        key = get_total_cap_key(offer_id, publisher_id)
        try:
            # 使用 Lua 脚本原子化 decr + 负数归零，避免并发 set 覆盖丢失计数
            val = await redis.eval(RedisCapManager._DECREMENT_LUA, 1, key)
            return int(val)
        except Exception as e:
            logger.error(f"Redis回滚失败: {e}", exc_info=True)
            return -1
