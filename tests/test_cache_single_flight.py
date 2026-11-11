"""缓存单飞：同 key 并发未命中只执行一次 factory。"""
from __future__ import annotations

import asyncio

import pytest

from app.core.infrastructure import cache_compat as cache_compat_mod
from app.core.infrastructure.cache_compat import get_or_set_single_flight


@pytest.mark.asyncio
async def test_get_or_set_single_flight_coalesces_concurrent_miss(monkeypatch):
    calls = {"n": 0}
    store: dict[str, object] = {}

    async def fake_get(key: str, key_prefix: str = "query_cache"):
        return store.get(key)

    async def fake_set(key: str, value, ttl: int = 300, key_prefix: str = "query_cache"):
        store[key] = value
        return True

    monkeypatch.setattr(cache_compat_mod, "legacy_get_cached", fake_get)
    monkeypatch.setattr(cache_compat_mod, "legacy_set_cached", fake_set)
    cache_compat_mod._inflight_futures.clear()

    async def factory():
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return {"ok": True, "n": calls["n"]}

    async def _one():
        return await get_or_set_single_flight(
            "sf_test_key",
            factory,
            ttl=60,
            key_prefix="ad_data",
            is_valid=lambda c: isinstance(c, dict) and c.get("ok") is True,
        )

    results = await asyncio.gather(*[_one() for _ in range(8)])
    assert calls["n"] == 1
    assert all(r == results[0] for r in results)
    assert results[0]["ok"] is True
    assert store["sf_test_key"]["ok"] is True


@pytest.mark.asyncio
async def test_get_or_set_single_flight_hit_skips_factory(monkeypatch):
    store = {"sf_hit_key": {"ok": True, "from": "cache"}}
    calls = {"n": 0}

    async def fake_get(key: str, key_prefix: str = "query_cache"):
        return store.get(key)

    async def fake_set(key: str, value, ttl: int = 300, key_prefix: str = "query_cache"):
        store[key] = value
        return True

    monkeypatch.setattr(cache_compat_mod, "legacy_get_cached", fake_get)
    monkeypatch.setattr(cache_compat_mod, "legacy_set_cached", fake_set)

    async def factory():
        calls["n"] += 1
        return {"ok": True, "from": "factory"}

    out = await get_or_set_single_flight(
        "sf_hit_key",
        factory,
        ttl=60,
        is_valid=lambda c: isinstance(c, dict) and c.get("ok") is True,
    )
    assert out["from"] == "cache"
    assert calls["n"] == 0



def test_single_flight_state_is_isolated_between_event_loops():
    async def get_state():
        return cache_compat_mod._get_inflight_state()

    cache_compat_mod._inflight_futures.clear()

    lock_a, futures_a = asyncio.run(get_state())
    lock_b, futures_b = asyncio.run(get_state())

    assert lock_a is not lock_b
    assert futures_a is not futures_b



@pytest.mark.asyncio
async def test_distributed_lock_release_uses_atomic_owner_check(monkeypatch):
    """锁到期后被新请求重获时，旧 owner 释放不得删除新锁。"""
    from app.core.infrastructure import cache_advanced as cache_advanced_mod

    class FakeRedis:
        def __init__(self):
            self.values = {}
            self.eval_calls = 0

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in self.values:
                return None
            self.values[key] = value
            return True

        async def eval(self, script, numkeys, key, owner):
            self.eval_calls += 1
            # 模拟旧锁刚过期、新 owner 已经拿到同一个 key 的交错时序。
            self.values[key] = "new-owner-token"
            if self.values.get(key) == owner:
                del self.values[key]
                return 1
            return 0

    class FakeCache:
        def __init__(self, redis):
            self.redis = redis

    redis = FakeRedis()
    monkeypatch.setattr(
        cache_advanced_mod, "get_cache_backend",
        lambda: _async_value(FakeCache(redis)),
    )

    lock = cache_advanced_mod.DistributedLock("single-flight-race", timeout=10)
    assert len(lock.lock_value) >= 32
    assert await lock.acquire() is True

    # 释放脚本发现 key 已属于新 owner，必须保留新 owner 的锁。
    assert await lock.release() is False
    assert redis.eval_calls == 1
    assert redis.values[lock.key] == "new-owner-token"


@pytest.mark.asyncio
async def test_distributed_lock_owner_tokens_are_unique():
    from app.core.infrastructure.cache_advanced import DistributedLock

    first = DistributedLock("token-uniqueness")
    second = DistributedLock("token-uniqueness")
    assert first.lock_value != second.lock_value


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_memory_cache_fallback_uses_process_local_lock(monkeypatch):
    """Redis 降级时同一事件循环内同 key 仍应互斥，不得伪装成分布式锁。"""
    from app.core.infrastructure import cache_advanced as cache_advanced_mod

    class FakeMemoryCache:
        # MemoryCacheBackend 不含 redis 属性。
        pass

    cache = FakeMemoryCache()
    monkeypatch.setattr(
        cache_advanced_mod,
        "get_cache_backend",
        lambda: _async_value(cache),
    )

    first = cache_advanced_mod.DistributedLock("memory-fallback-key", timeout=10)
    second = cache_advanced_mod.DistributedLock("memory-fallback-key", timeout=10)

    assert await first.acquire() is True
    assert await second.acquire() is False
    assert await first.release() is True
    assert await second.acquire() is True
    assert await second.release() is True
