"""Redis 缓存后端故障切换与自动恢复回归测试。"""
from __future__ import annotations

import pytest

from app.core.infrastructure import cache as cache_module


class FakeRedis:
    """只用于验证后端选择，不模拟 Redis 命令行为。"""


@pytest.mark.asyncio
async def test_cache_backend_recovers_when_redis_becomes_available(monkeypatch):
    """应用启动时 Redis 不可用，后续恢复后应自动切回共享 Redis 后端。"""
    state = {"client": None}
    loop = __import__("asyncio").get_running_loop()

    async def fake_get_redis_client():
        return state["client"]

    monkeypatch.setattr(cache_module, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(cache_module, "_cache_backend", None)
    monkeypatch.setattr(cache_module, "_cache_loop", loop)

    fallback = await cache_module.get_cache_backend()
    assert isinstance(fallback, cache_module.MemoryCacheBackend)

    redis = FakeRedis()
    state["client"] = redis

    recovered = await cache_module.get_cache_backend()
    assert isinstance(recovered, cache_module.RedisCacheBackend)
    assert recovered.redis is redis


@pytest.mark.asyncio
async def test_cache_backend_switches_to_memory_and_recovers_after_runtime_outage(monkeypatch):
    """运行中 Redis 断连切换到内存后，恢复时应重新绑定健康 Redis 客户端。"""
    state = {"client": FakeRedis()}
    loop = __import__("asyncio").get_running_loop()

    async def fake_get_redis_client():
        return state["client"]

    monkeypatch.setattr(cache_module, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(cache_module, "_cache_backend", None)
    monkeypatch.setattr(cache_module, "_cache_loop", loop)

    first_redis = state["client"]
    connected = await cache_module.get_cache_backend()
    assert isinstance(connected, cache_module.RedisCacheBackend)
    assert connected.redis is first_redis

    state["client"] = None
    fallback = await cache_module.get_cache_backend()
    assert isinstance(fallback, cache_module.MemoryCacheBackend)

    recovered_redis = FakeRedis()
    state["client"] = recovered_redis
    recovered = await cache_module.get_cache_backend()
    assert isinstance(recovered, cache_module.RedisCacheBackend)
    assert recovered.redis is recovered_redis
