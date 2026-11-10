"""Redis 客户端获取热路径回归测试。"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.core import redis_client


@pytest.mark.asyncio
async def test_get_redis_client_hot_path_does_not_ping_every_request(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.ping_calls = 0

        async def ping(self):
            self.ping_calls += 1
            return True

    fake = FakeRedis()
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(redis_client, "_redis_client", fake)
    monkeypatch.setattr(redis_client, "_redis_loop", loop)
    monkeypatch.setattr(redis_client, "_redis_last_ping_at", time.monotonic())
    monkeypatch.setattr(redis_client, "_redis_connect_backoff_until", 0.0)
    monkeypatch.setattr(redis_client, "_redis_connect_lock", asyncio.Lock())

    first = await redis_client.get_redis_client()
    second = await redis_client.get_redis_client()

    assert first is fake
    assert second is fake
    assert fake.ping_calls == 0


@pytest.mark.asyncio
async def test_get_redis_client_performs_low_frequency_health_ping(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.ping_calls = 0

        async def ping(self):
            self.ping_calls += 1
            return True

    fake = FakeRedis()
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(redis_client, "_redis_client", fake)
    monkeypatch.setattr(redis_client, "_redis_loop", loop)
    monkeypatch.setattr(
        redis_client,
        "_redis_last_ping_at",
        time.monotonic() - redis_client._REDIS_EXPLICIT_PING_INTERVAL_SECONDS - 1,
    )
    monkeypatch.setattr(redis_client, "_redis_connect_backoff_until", 0.0)
    monkeypatch.setattr(redis_client, "_redis_connect_lock", asyncio.Lock())

    result = await redis_client.get_redis_client()

    assert result is fake
    assert fake.ping_calls == 1
    assert redis_client._redis_last_ping_at > 0
