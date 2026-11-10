"""
Redis Cap 计数器实现
用于高性能的 Cap 检查和计数

Key 结构:
cpl:cap:daily:{offer_id}:{date_str} -> int
cpl:cap:total:{offer_id} -> int
"""
import logging
import uuid
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


class _CapReservationStateLost(RuntimeError):
    """幂等令牌存在但计数状态丢失；必须 fail-closed，不能误判为成功或超限。"""


class RedisCapManager:
    """Redis Cap 管理器"""

    @staticmethod
    def _redis_unavailable_result() -> Optional[bool]:
        """Redis 不可用时返回三态结果；fail-open 放行但不伪造 reservation。"""
        if settings.CAP_FAIL_OPEN:
            logger.warning("Redis不可用，Cap fail-open 放行（未创建 Redis reservation）")
            return None
        logger.error("Redis不可用，Cap fail-close 拒绝")
        raise RuntimeError("Redis unavailable during Cap reservation")

    @staticmethod
    def _lua_failure_result() -> Optional[bool]:
        if settings.CAP_FAIL_OPEN:
            logger.warning("Redis Cap Lua 失败，fail-open 放行（未创建 Redis reservation）")
            return None
        logger.error("Redis Cap Lua 失败，fail-close 拒绝")
        raise RuntimeError("Redis Cap reservation Lua failed")
    
    # Lua：以唯一 reservation token 保证预留幂等；同一请求重试不会重复 INCR。
    # KEYS[1]: cap_key；KEYS[2]: reservation token key
    # ARGV[1]: expire_seconds；ARGV[2]: DB 初始值；ARGV[3]: limit
    _RESERVE_LUA = """
    local counter_ttl = tonumber(ARGV[1]) or 0
    local token_ttl = tonumber(ARGV[4]) or counter_ttl
    if redis.call('EXISTS', KEYS[2]) == 1 then
        -- token 仍在但 counter 已被独立淘汰/删除时，绝不能把缺失计数当作 0 放行。
        if redis.call('EXISTS', KEYS[1]) == 0 then
            return -2
        end
        local existing = tonumber(redis.call('GET', KEYS[1]))
        if not existing then
            return -2
        end
        -- 即使本次只是幂等重试，也必须清除历史 Total key 的旧 TTL。
        if counter_ttl > 0 then
            redis.call('EXPIRE', KEYS[1], counter_ttl)
        else
            redis.call('PERSIST', KEYS[1])
        end
        return existing
    end
    local limit = tonumber(ARGV[3])
    local db_count = tonumber(ARGV[2]) or 0
    local redis_value = redis.call('GET', KEYS[1])
    -- 达到上限时也必须清除旧 Total key 的 TTL，不能让满额计数器自动消失。
    if redis_value and counter_ttl == 0 then
        redis.call('PERSIST', KEYS[1])
    end
    local current = tonumber(redis_value)
    if not current then
        current = db_count
    else
        current = math.max(current, db_count)
    end
    if current >= limit then
        return -1
    end
    local new_val = current + 1
    -- Daily key 设置滚动 TTL；Total key 使用 counter_ttl=0，必须永久保留。
    redis.call('SET', KEYS[1], new_val)
    if counter_ttl > 0 then
        redis.call('EXPIRE', KEYS[1], counter_ttl)
    else
        -- 兼容旧版本遗留的 30 天 TTL，首次新代码预留时主动清除。
        redis.call('PERSIST', KEYS[1])
    end
    -- reservation token 独立过期，避免成功提交的请求留下永久 token。
    redis.call('SET', KEYS[2], '1')
    if token_ttl > 0 then
        redis.call('EXPIRE', KEYS[2], token_ttl)
    else
        redis.call('PERSIST', KEYS[2])
    end
    return new_val
    """

    # 仅当本次 token 仍存在时撤销一次；重复调用不会误减其他请求的计数。
    _ROLLBACK_RESERVATION_LUA = """
    if redis.call('EXISTS', KEYS[2]) == 0 then
        return 0
    end
    -- 计数器缺失可能是独立淘汰/重启；保留 token 作为恢复证据，
    -- 不能先删 token 再返回，否则永久丢失本次预留的撤销依据。
    if redis.call('EXISTS', KEYS[1]) == 0 then
        return -2
    end
    local current = tonumber(redis.call('GET', KEYS[1]) or '0')
    if not current then
        return -2
    end
    redis.call('DEL', KEYS[2])
    if current > 0 then
        return redis.call('DECR', KEYS[1])
    end
    return 0
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
        initial_value: Optional[int] = None,
        reservation_id: Optional[str] = None,
    ) -> Optional[bool]:
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
            token = reservation_id or uuid.uuid4().hex
            token_key = f"{key}:reservation:{token}"
            current = await redis.eval(
                RedisCapManager._RESERVE_LUA,
                2,
                key,
                token_key,
                DEFAULT_EXPIRE_SECONDS,
                init_val,
                str(limit),
                DEFAULT_EXPIRE_SECONDS,
            )
            current = int(current)
            if current == -2:
                raise _CapReservationStateLost("Redis 日 Cap token 存在但计数 key 丢失，拒绝重试放行")
            if current < 0:
                return False
            return True
        except _CapReservationStateLost:
            raise
        except Exception as e:
            logger.error("Redis 日 Cap 预留结果不确定，使用唯一令牌执行幂等补偿：%s", e, exc_info=True)
            try:
                rolled_back = await RedisCapManager.decrement_daily(
                    offer_id, publisher_id, reservation_date=now,
                    reservation_id=token,
                )
            except Exception:
                rolled_back = -1
            if rolled_back < 0:
                raise RuntimeError("Redis 日 Cap 预留结果不确定且令牌补偿失败") from e
            return RedisCapManager._lua_failure_result()

    @staticmethod
    async def check_and_increment_total(
        offer_id: int, 
        limit: int, 
        publisher_id: Optional[int] = None,
        initial_value: Optional[int] = None,
        reservation_id: Optional[str] = None,
    ) -> Optional[bool]:
        """
        检查并增加总计数
        """
        redis = await get_redis_client()
        if not redis:
            return RedisCapManager._redis_unavailable_result()
            
        key = get_total_cap_key(offer_id, publisher_id)
        
        try:
            init_val = str(initial_value) if initial_value is not None else "0"
            token = reservation_id or uuid.uuid4().hex
            token_key = f"{key}:reservation:{token}"
            current = await redis.eval(
                RedisCapManager._RESERVE_LUA,
                2,
                key,
                token_key,
                0,  # Total Cap 计数器不能自动过期。
                init_val,
                str(limit),
                30 * 24 * 3600,  # reservation token 独立保留 30 天。
            )
            current = int(current)
            if current == -2:
                raise _CapReservationStateLost("Redis 总 Cap token 存在但计数 key 丢失，拒绝重试放行")
            if current < 0:
                return False
            return True
        except _CapReservationStateLost:
            raise
        except Exception as e:
            logger.error("Redis 总 Cap 预留结果不确定，使用唯一令牌执行幂等补偿：%s", e, exc_info=True)
            try:
                rolled_back = await RedisCapManager.decrement_total(
                    offer_id, publisher_id, reservation_id=token,
                )
            except Exception:
                rolled_back = -1
            if rolled_back < 0:
                raise RuntimeError("Redis 总 Cap 预留结果不确定且令牌补偿失败") from e
            return RedisCapManager._lua_failure_result()
            
    @staticmethod
    async def decrement_daily(
        offer_id: int,
        publisher_id: Optional[int] = None,
        reservation_date: Optional[datetime] = None,
        reservation_id: Optional[str] = None,
    ) -> int:
        """按原业务日期回退日 Cap；带 token 时保证同一预留最多回退一次。"""
        redis = await get_redis_client()
        if not redis:
            return -1
        key_date = reservation_date or get_app_now_naive()
        key = get_daily_cap_key(offer_id, key_date, publisher_id)
        try:
            if reservation_id:
                token_key = f"{key}:reservation:{reservation_id}"
                val = await redis.eval(
                    RedisCapManager._ROLLBACK_RESERVATION_LUA, 2, key, token_key
                )
            else:
                val = await redis.eval(RedisCapManager._DECREMENT_LUA, 1, key)
            return int(val)
        except Exception as e:
            logger.error("Redis 日 Cap 回滚失败：%s", e, exc_info=True)
            return -1

    @staticmethod
    async def decrement_total(
        offer_id: int,
        publisher_id: Optional[int] = None,
        reservation_id: Optional[str] = None,
    ) -> int:
        """回退总 Cap；带 token 时保证同一预留最多回退一次。"""
        redis = await get_redis_client()
        if not redis:
            return -1
        key = get_total_cap_key(offer_id, publisher_id)
        try:
            if reservation_id:
                token_key = f"{key}:reservation:{reservation_id}"
                val = await redis.eval(
                    RedisCapManager._ROLLBACK_RESERVATION_LUA, 2, key, token_key
                )
            else:
                val = await redis.eval(RedisCapManager._DECREMENT_LUA, 1, key)
            return int(val)
        except Exception as e:
            logger.error("Redis 总 Cap 回滚失败：%s", e, exc_info=True)
            return -1
