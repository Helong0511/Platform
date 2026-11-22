"""REDIS_URL 环境配置兼容性回归测试。"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core import redis_client


@pytest.mark.asyncio
async def test_get_redis_client_uses_env_example_redis_url_without_redis_host(monkeypatch):
    """仅按 .env.example 配置 REDIS_URL 时，生产环境必须实际连接 Redis。"""
    loop = asyncio.get_running_loop()
    created = {}

    class FakeRedis:
        async def ping(self):
            return True

    fake = FakeRedis()

    def fake_from_url(url, **kwargs):
        created["url"] = url
        created["kwargs"] = kwargs
        return fake

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
            REDIS_HOST=None,
            REDIS_URL="rediss://redis.example.invalid:6380/15",
            REDIS_PORT=6379,
            REDIS_DB=0,
            REDIS_PASSWORD="injected-secret",
            REDIS_MAX_CONNECTIONS=7,
        ),
    )
    monkeypatch.setattr(
        redis_client,
        "aioredis",
        SimpleNamespace(from_url=fake_from_url),
    )

    result = await redis_client.get_redis_client()

    assert result is fake
    assert created["url"] == "rediss://redis.example.invalid:6380/15"
    assert created["kwargs"]["password"] == "injected-secret"
    assert created["kwargs"]["max_connections"] == 7
    assert created["kwargs"]["decode_responses"] is True
    assert redis_client._redis_loop is loop


@pytest.mark.asyncio
async def test_invalid_redis_url_fails_closed_without_creating_client(monkeypatch):
    """错误 URL 不得静默连接默认 localhost 或创建伪客户端。"""
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
            REDIS_HOST=None,
            REDIS_URL="http://redis.example.invalid:6379/0",
            REDIS_PORT=6379,
            REDIS_DB=0,
            REDIS_PASSWORD=None,
            REDIS_MAX_CONNECTIONS=5,
        ),
    )

    def unexpected_from_url(*args, **kwargs):
        raise AssertionError("invalid URL must not create a Redis client")

    monkeypatch.setattr(
        redis_client,
        "aioredis",
        SimpleNamespace(from_url=unexpected_from_url),
    )

    assert await redis_client.get_redis_client() is None
    assert redis_client._redis_client is None
