"""Cap reservation token must make ambiguous reserve and repeated rollback safe."""
from datetime import datetime

import pytest

from app.core.cap import redis_counter


class _AmbiguousRedis:
    def __init__(self):
        self.values = {}
        self.tokens = set()
        self.reserve_calls = 0
        self.rollback_calls = 0

    async def eval(self, script, numkeys, *args):
        if script == redis_counter.RedisCapManager._RESERVE_LUA:
            self.reserve_calls += 1
            key, token_key, ttl, initial, limit = args
            if token_key in self.tokens:
                return int(self.values.get(key, 0))
            current = max(int(self.values.get(key, initial)), int(initial))
            if current >= int(limit):
                return -1
            self.values[key] = current + 1
            self.tokens.add(token_key)
            # 模拟 Redis 已执行 Lua，但响应在网络中丢失。
            raise OSError("simulated lost Redis response after execution")

        if script == redis_counter.RedisCapManager._ROLLBACK_RESERVATION_LUA:
            self.rollback_calls += 1
            key, token_key = args
            if token_key not in self.tokens:
                return 0
            self.tokens.remove(token_key)
            if key in self.values and self.values[key] > 0:
                self.values[key] -= 1
            return self.values.get(key, 0)

        raise AssertionError("unexpected Redis Lua script")


@pytest.mark.asyncio
async def test_ambiguous_daily_reservation_is_compensated_by_token(monkeypatch):
    redis = _AmbiguousRedis()
    now = datetime(2026, 11, 10, 12, 0, 0)

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter, "get_app_now_naive", lambda: now)
    monkeypatch.setattr(redis_counter.settings, "CAP_FAIL_OPEN", True)

    result = await redis_counter.RedisCapManager.check_and_increment_daily(
        offer_id=77,
        limit=100,
        publisher_id=12,
        initial_value=5,
        reservation_id="request-token-001",
    )

    key = redis_counter.get_daily_cap_key(77, now, 12)
    token_key = f"{key}:reservation:request-token-001"
    assert result is None
    assert redis.values[key] == 5
    assert token_key not in redis.tokens
    assert redis.reserve_calls == 1
    assert redis.rollback_calls == 1


@pytest.mark.asyncio
async def test_repeated_token_rollback_never_decrements_another_request(monkeypatch):
    redis = _AmbiguousRedis()
    now = datetime(2026, 11, 10, 12, 0, 0)
    key = redis_counter.get_daily_cap_key(77, now, 12)
    own_token = f"{key}:reservation:own"
    other_token = f"{key}:reservation:other"
    redis.values[key] = 2
    redis.tokens.update({own_token, other_token})

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter, "get_app_now_naive", lambda: now)

    first = await redis_counter.RedisCapManager.decrement_daily(
        77, 12, reservation_date=now, reservation_id="own"
    )
    second = await redis_counter.RedisCapManager.decrement_daily(
        77, 12, reservation_date=now, reservation_id="own"
    )

    assert first == 1
    assert second == 0  # token 已在第一次调用中删除，重复回滚不再扣减
    assert redis.values[key] == 1
    assert other_token in redis.tokens
