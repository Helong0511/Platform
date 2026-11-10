"""缓存单飞：同 key 并发未命中只执行一次 factory。"""
from __future__ import annotations

import asyncio

import pytest

from app.core.infrastructure import cache as cache_mod
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
    cache_compat_mod._inflight_locks.clear()

    lock_a, futures_a = asyncio.run(get_state())
    lock_b, futures_b = asyncio.run(get_state())

    assert lock_a is not lock_b
    assert futures_a is not futures_b


@pytest.mark.asyncio
async def test_cache_backend_is_stable_per_loop_and_isolated_across_loops(monkeypatch):
    async def fake_get_redis_client():
        return object()

    monkeypatch.setattr(cache_mod, "get_redis_client", fake_get_redis_client)
    cache_mod._cache_backends.clear()
    cache_mod._cache_locks.clear()

    async def get_twice():
        first = await cache_mod.get_cache_backend()
        second = await cache_mod.get_cache_backend()
        return first, second

    loop_a_first, loop_a_second = await get_twice()
    loop_b_first, loop_b_second = await asyncio.to_thread(
        lambda: asyncio.run(get_twice())
    )

    assert loop_a_first is loop_a_second
    assert loop_b_first is loop_b_second
    assert loop_a_first is not loop_b_first
