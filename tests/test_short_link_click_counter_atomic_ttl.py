"""短链接点击计数 Redis 原子性回归测试。"""
from __future__ import annotations

import pytest

from app.core import short_link_click_counter as counter


@pytest.mark.asyncio
async def test_increment_uses_single_atomic_redis_script(monkeypatch):
    calls = []

    class FakeRedis:
        async def eval(self, script, number_of_keys, key, ttl):
            calls.append((script, number_of_keys, key, ttl))
            return 7

    async def fake_get_redis_client():
        return FakeRedis()

    monkeypatch.setattr(counter, "get_redis_client", fake_get_redis_client)
    await counter.increment_click_count_async("regression-code")

    assert len(calls) == 1
    script, number_of_keys, key, ttl = calls[0]
    assert number_of_keys == 1
    assert key == f"{counter.CLICK_COUNTER_PREFIX}regression-code"
    assert ttl == 48 * 3600
    assert "redis.call('INCR', KEYS[1])" in script
    assert "redis.call('EXPIRE', KEYS[1], ARGV[1])" in script
