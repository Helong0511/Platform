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


def test_decrement_script_preserves_ttl_without_replacing_key():
    # Redis DECRBY 不会清除现有 TTL；SET 默认会清除 TTL。
    script = counter._DECREMENT_COUNTER_LUA
    assert "redis.call('DECRBY', KEYS[1], decrement)" in script
    assert "redis.call('SET'" not in script
    assert "redis.call('DEL', KEYS[1])" in script


@pytest.mark.asyncio
async def test_scan_counter_keys_deduplicates_scan_results():
    class FakeRedis:
        def __init__(self):
            self.calls = 0

        async def scan(self, cursor, match, count):
            self.calls += 1
            if self.calls == 1:
                return 1, ["short_link:click:a", "short_link:click:b"]
            return 0, ["short_link:click:b", "short_link:click:c"]

        async def keys(self, pattern):
            raise AssertionError("SCAN path must never fall back to KEYS")

    redis = FakeRedis()
    keys = await counter._scan_click_counter_keys(redis, max_keys=10)
    assert keys == [
        "short_link:click:a",
        "short_link:click:b",
        "short_link:click:c",
    ]


@pytest.mark.asyncio
async def test_scan_failure_does_not_fall_back_to_blocking_keys():
    class FakeRedis:
        def __init__(self):
            self.keys_called = False

        async def scan(self, cursor, match, count):
            raise OSError("simulated isolated Redis scan failure")

        async def keys(self, pattern):
            self.keys_called = True
            raise AssertionError("KEYS fallback is forbidden")

    redis = FakeRedis()
    keys = await counter._scan_click_counter_keys(redis, max_keys=10)
    assert keys == []
    assert redis.keys_called is False
