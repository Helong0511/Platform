"""Redis 客户端获取热路径回归测试。"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

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



@pytest.mark.asyncio
async def test_get_redis_client_initializes_connection_lock_loop(monkeypatch):
    """首次连接时必须初始化锁及其事件循环归属，不能读取未定义全局变量。"""
    class FakeRedis:
        def __init__(self):
            self.ping_calls = 0

        async def ping(self):
            self.ping_calls += 1
            return True

    fake = FakeRedis()
    loop = asyncio.get_running_loop()

    monkeypatch.setattr(redis_client, "_redis_client", None)
    monkeypatch.setattr(redis_client, "_redis_loop", None)
    monkeypatch.setattr(redis_client, "_redis_connect_lock", None)
    monkeypatch.setattr(redis_client, "_redis_connect_lock_loop", None)
    monkeypatch.setattr(redis_client, "_redis_connect_backoff_until", 0.0)
    monkeypatch.setattr(redis_client, "REDIS_AVAILABLE", True)
    monkeypatch.setattr(
        redis_client,
        "settings",
        SimpleNamespace(
            is_production=True,
            REDIS_HOST="192.0.2.10",
            REDIS_PORT=6379,
            REDIS_DB=15,
            REDIS_PASSWORD=None,
            REDIS_MAX_CONNECTIONS=5,
        ),
    )
    monkeypatch.setattr(
        redis_client,
        "aioredis",
        SimpleNamespace(Redis=lambda **kwargs: fake),
    )

    result = await redis_client.get_redis_client()

    assert result is fake
    assert fake.ping_calls == 1
    assert redis_client._redis_connect_lock is not None
    assert redis_client._redis_connect_lock_loop is loop
    assert redis_client._redis_loop is loop
