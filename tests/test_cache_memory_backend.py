"""内存缓存降级后端容量与过期行为回归测试。"""
import pytest

from app.core.infrastructure.cache import MemoryCacheBackend


@pytest.mark.asyncio
async def test_memory_cache_evicts_least_recently_used_entry():
    cache = MemoryCacheBackend(max_entries=2)

    assert await cache.set("a", 1) is True
    assert await cache.set("b", 2) is True
    assert await cache.get("a") == 1  # a 成为最近访问项
    assert await cache.set("c", 3) is True

    assert len(cache._cache) == 2
    assert await cache.get("a") == 1
    assert await cache.get("b") is None
    assert await cache.get("c") == 3


@pytest.mark.asyncio
async def test_memory_cache_capacity_sweep_removes_expired_entries(monkeypatch):
    cache = MemoryCacheBackend(max_entries=2)
    now = {"value": 100.0}
    monkeypatch.setattr(cache, "_time", lambda: now["value"])

    await cache.set("expired", "old", ttl=1)
    await cache.set("live", "keep", ttl=100)
    now["value"] = 102.0

    # 新写入使容量暂时超限，应先清除过期项，不误淘汰仍有效的数据。
    await cache.set("new", "value", ttl=100)

    assert len(cache._cache) == 2
    assert await cache.get("expired") is None
    assert await cache.get("live") == "keep"
    assert await cache.get("new") == "value"


@pytest.mark.asyncio
async def test_memory_cache_rejects_unbounded_capacity_configuration():
    cache = MemoryCacheBackend(max_entries=0)
    assert cache._max_entries == 1
    await cache.set("only", "value")
    await cache.set("second", "value")
    assert len(cache._cache) == 1
    assert await cache.get("only") is None
    assert await cache.get("second") == "value"
