"""客户开放 API 签名请求防重放回归测试。"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import api_auth


class _Scalars:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _Result:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return _Scalars(self.value)


class _DB:
    def __init__(self, client):
        self.client = client

    async def execute(self, statement):
        return _Result(self.client)


class _ReplayStore:
    def __init__(self):
        self.values = {}
        self.calls = []

    async def set(self, key, value, *, ex, nx):
        self.calls.append((key, value, ex, nx))
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True


def _client(client_id=17):
    return SimpleNamespace(
        id=client_id,
        is_active=True,
        api_enabled=True,
        key="synthetic-client-secret",
        allowed_ips="",
    )


def _request(sign="synthetic-signature"):
    return SimpleNamespace(
        client_id=17,
        req_time=int(datetime.now(timezone.utc).timestamp()),
        sign=sign,
    )


@pytest.mark.asyncio
async def test_same_signed_request_is_claimed_once_and_replay_is_rejected(monkeypatch):
    store = _ReplayStore()

    async def get_store():
        return store

    monkeypatch.setattr(api_auth, "get_redis_client", get_store)
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)
    request = _request()

    first = await api_auth.verify_client_request(
        request, _DB(_client()), client_ip="198.51.100.7"
    )
    assert first.id == 17

    with pytest.raises(HTTPException) as caught:
        await api_auth.verify_client_request(
            request, _DB(_client()), client_ip="198.51.100.7"
        )

    assert caught.value.status_code == 409
    assert len(store.calls) == 2
    assert store.calls[0][2] == 31  # 覆盖 req_time ± 15 秒的完整有效窗口
    assert store.calls[0][3] is True
    assert "请求已使用" in str(caught.value.detail)


@pytest.mark.asyncio
async def test_replay_fingerprint_is_scoped_to_client_id(monkeypatch):
    store = _ReplayStore()

    async def get_store():
        return store

    monkeypatch.setattr(api_auth, "get_redis_client", get_store)
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)
    request = _request()

    await api_auth.verify_client_request(
        request, _DB(_client(17)), client_ip="198.51.100.7"
    )
    other_request = SimpleNamespace(
        client_id=18,
        req_time=request.req_time,
        sign=request.sign,
    )
    result = await api_auth.verify_client_request(
        other_request, _DB(_client(18)), client_ip="198.51.100.7"
    )

    assert result.id == 18
    assert len(store.values) == 2


@pytest.mark.asyncio
async def test_replay_store_unavailable_fails_closed(monkeypatch):
    async def no_store():
        return None

    monkeypatch.setattr(api_auth, "get_redis_client", no_store)
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)

    with pytest.raises(HTTPException) as caught:
        await api_auth.verify_client_request(
            _request(), _DB(_client()), client_ip="198.51.100.7"
        )

    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_replay_store_write_error_fails_closed(monkeypatch):
    class BrokenStore:
        async def set(self, *args, **kwargs):
            raise OSError("synthetic Redis outage")

    async def get_store():
        return BrokenStore()

    monkeypatch.setattr(api_auth, "get_redis_client", get_store)
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)

    with pytest.raises(HTTPException) as caught:
        await api_auth.verify_client_request(
            _request(), _DB(_client()), client_ip="198.51.100.7"
        )

    assert caught.value.status_code == 503
    assert "synthetic Redis outage" not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_invalid_signature_does_not_consume_replay_key(monkeypatch):
    class UnusedStore:
        async def set(self, *args, **kwargs):
            pytest.fail("invalid signatures must not consume replay keys")

    async def get_store():
        return UnusedStore()

    monkeypatch.setattr(api_auth, "get_redis_client", get_store)
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: False)

    with pytest.raises(HTTPException):
        await api_auth.verify_client_request(
            _request(), _DB(_client()), client_ip="198.51.100.7"
        )


# 真实 Redis 集成测试仅允许 GitHub Actions 临时 Redis DB14。
import ipaddress
import os
from urllib.parse import urlsplit

from redis.asyncio import Redis


REDIS_URL = os.getenv("REDIS_INTEGRATION_URL")


def _is_loopback_redis_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if not host:
            return False
        if host.strip().lower() == "localhost":
            loopback = True
        else:
            try:
                loopback = ipaddress.ip_address(host.strip()).is_loopback
            except ValueError:
                loopback = False
        return (
            parsed.scheme in {"redis", "rediss"}
            and loopback
            and parsed.port in (None, 6379)
            and parsed.path.strip("/") == "14"
        )
    except ValueError:
        return False


_SAFE_REDIS_TARGET = (
    os.getenv("UNIT_TEST") == "1"
    and os.getenv("GITHUB_ACTIONS") == "true"
    and os.getenv("REDIS_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _is_loopback_redis_url(REDIS_URL)
)

if (
    os.getenv("GITHUB_ACTIONS") == "true"
    or (os.getenv("UNIT_TEST") == "1" and REDIS_URL)
) and not _SAFE_REDIS_TARGET:
    raise RuntimeError(
        "拒绝执行客户 API 防重放 Redis 集成测试：仅允许 loopback Redis DB14，"
        "并显式启用 REDIS_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS=1"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _SAFE_REDIS_TARGET,
    reason="仅在 GitHub Actions 临时 Redis DB14 中运行",
)
async def test_real_redis_set_nx_prevents_client_api_signed_request_replay(monkeypatch):
    """真实 Redis 验证防重放键的跨请求原子唯一认领。"""
    import hashlib
    import uuid

    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    client_id = 17
    req_time = int(datetime.now(timezone.utc).timestamp())
    sign = f"synthetic-{uuid.uuid4().hex}"
    fingerprint = hashlib.sha256(
        f"{client_id}:{req_time}:{sign.lower()}".encode("utf-8")
    ).hexdigest()
    redis_key = f"client_api:replay:v1:{fingerprint}"

    async def isolated_redis_client():
        return redis

    monkeypatch.setattr(api_auth, "get_redis_client", isolated_redis_client)
    try:
        assert await redis.ping() is True
        import asyncio

        outcomes = await asyncio.gather(
            *[
                api_auth._claim_client_api_request(
                    client_id=client_id,
                    req_time=req_time,
                    sign=sign,
                    time_tolerance=15,
                )
                for _ in range(2)
            ],
            return_exceptions=True,
        )
        accepted = [item for item in outcomes if item is None]
        conflicts = [
            item
            for item in outcomes
            if isinstance(item, HTTPException) and item.status_code == 409
        ]
        assert len(accepted) == 1
        assert len(conflicts) == 1
        assert await redis.get(redis_key) == "1"
        assert 1 <= await redis.ttl(redis_key) <= 31
    finally:
        await redis.delete(redis_key)
        await redis.aclose()


@pytest.mark.asyncio
async def test_replay_store_client_lookup_error_fails_closed(monkeypatch):
    async def broken_lookup():
        raise OSError("synthetic Redis discovery failure")

    monkeypatch.setattr(api_auth, "get_redis_client", broken_lookup)
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)

    with pytest.raises(HTTPException) as caught:
        await api_auth.verify_client_request(
            _request(), _DB(_client()), client_ip="198.51.100.7"
        )

    assert caught.value.status_code == 503
    assert "synthetic Redis discovery failure" not in str(caught.value.detail)
