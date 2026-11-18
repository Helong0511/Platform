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
