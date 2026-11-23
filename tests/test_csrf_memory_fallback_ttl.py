"""CSRF Redis 权威存储与内存降级 TTL 回归测试。"""
import time
from unittest.mock import AsyncMock

import pytest

from app.core import csrf


class _RedisMiss:
    async def get(self, key):
        return None


class _RedisHit:
    async def get(self, key):
        return "redis-token"


class _RedisStore:
    def __init__(self):
        self.args = None

    async def setex(self, *args):
        self.args = args


@pytest.fixture(autouse=True)
def _clear_csrf_memory_store():
    csrf._csrf_tokens.clear()
    yield
    csrf._csrf_tokens.clear()


@pytest.mark.asyncio
async def test_redis_authoritative_miss_does_not_revive_stale_memory_token(monkeypatch):
    csrf._csrf_tokens["session-1"] = ("expired-token", time.monotonic() + 3600)
    monkeypatch.setattr(csrf, "get_redis_client", AsyncMock(return_value=_RedisMiss()))
    helper = csrf.CSRFMiddleware(lambda scope, receive, send: None)

    token = await helper._retrieve_csrf_token("session-1", None)

    assert token is None
    assert "session-1" not in csrf._csrf_tokens


@pytest.mark.asyncio
async def test_memory_fallback_rejects_expired_token_when_redis_unavailable(monkeypatch):
    csrf._csrf_tokens["session-2"] = ("expired-token", time.monotonic() - 1)
    monkeypatch.setattr(csrf, "get_redis_client", AsyncMock(return_value=None))
    helper = csrf.CSRFMiddleware(lambda scope, receive, send: None)

    token = await helper._retrieve_csrf_token("session-2", None)

    assert token is None
    assert "session-2" not in csrf._csrf_tokens


@pytest.mark.asyncio
async def test_redis_hit_is_not_copied_into_unbounded_memory_fallback(monkeypatch):
    monkeypatch.setattr(csrf, "get_redis_client", AsyncMock(return_value=_RedisHit()))
    helper = csrf.CSRFMiddleware(lambda scope, receive, send: None)

    token = await helper._retrieve_csrf_token("session-3", None)

    assert token == "redis-token"
    assert "session-3" not in csrf._csrf_tokens


@pytest.mark.asyncio
async def test_memory_fallback_store_records_expiry(monkeypatch):
    monkeypatch.setattr(csrf, "get_redis_client", AsyncMock(return_value=None))
    helper = csrf.CSRFMiddleware(lambda scope, receive, send: None)

    await helper._store_csrf_token("session-4", "local-token", None)

    token, expires_at = csrf._csrf_tokens["session-4"]
    assert token == "local-token"
    assert expires_at > time.monotonic()
