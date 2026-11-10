"""Redis 计数器 TTL 原子性回归测试。"""
from __future__ import annotations

import pytest

from app.core import middleware
from app.core.cap.redis_counter import RedisCapManager


@pytest.mark.asyncio
async def test_rate_limit_increment_and_expiry_are_atomic():
    calls = []

    class FakeRedis:
        async def eval(self, script, number_of_keys, key, ttl):
            calls.append((script, number_of_keys, key, ttl))
            return 4

    result = await middleware._increment_rate_limit_counter(
        FakeRedis(),
        "rate_limit:api:127.0.0.1:123",
        60,
    )

    assert result == 4
    assert len(calls) == 1
    script, number_of_keys, key, ttl = calls[0]
    assert number_of_keys == 1
    assert key == "rate_limit:api:127.0.0.1:123"
    assert ttl == 60
    assert "redis.call('INCR', KEYS[1])" in script
    assert "redis.call('EXPIRE', KEYS[1], ARGV[1])" in script
    assert "redis.call('TTL', KEYS[1]) < 0" in script


def test_cap_rollback_does_not_clear_expiration_or_create_missing_key():
    script = RedisCapManager._DECREMENT_LUA
    assert "redis.call('GET', KEYS[1])" in script
    assert "if not current then" in script
    assert "redis.call('DECR', KEYS[1])" in script
    assert "redis.call('INCR', KEYS[1])" in script
    assert "redis.call('SET'" not in script
