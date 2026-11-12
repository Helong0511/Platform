"""客户 API IP 白名单校验回归测试。"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import api_auth


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value


class FakeDB:
    def __init__(self, client):
        self.client = client

    async def execute(self, statement):
        return FakeResult(self.client)


def make_client(allowed_ips):
    return SimpleNamespace(
        id=17,
        is_active=True,
        api_enabled=True,
        key="isolated-client-secret",
        allowed_ips=allowed_ips,
    )


def make_request():
    return SimpleNamespace(
        client_id=17,
        req_time=int(datetime.now(timezone.utc).timestamp()),
        sign="isolated-signature",
    )


@pytest.mark.asyncio
async def test_client_api_allows_ip_in_configured_allowlist(monkeypatch):
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)
    client = make_client("192.0.2.10, 198.51.100.7")

    result = await api_auth.verify_client_request(
        make_request(),
        FakeDB(client),
        client_ip="192.0.2.10",
    )

    assert result is client


@pytest.mark.asyncio
async def test_client_api_rejects_ip_outside_configured_allowlist(monkeypatch):
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)
    client = make_client("192.0.2.10")

    with pytest.raises(HTTPException) as caught:
        await api_auth.verify_client_request(
            make_request(),
            FakeDB(client),
            client_ip="198.51.100.9",
        )

    assert caught.value.status_code == 403
    assert "不在客户 API 允许列表中" in str(caught.value.detail)


@pytest.mark.asyncio
async def test_client_api_empty_allowlist_preserves_unrestricted_compatibility(monkeypatch):
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)
    client = make_client("  ")

    result = await api_auth.verify_client_request(
        make_request(),
        FakeDB(client),
        client_ip="198.51.100.9",
    )

    assert result is client


@pytest.mark.asyncio
async def test_client_api_invalid_allowlist_fails_closed(monkeypatch):
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)
    client = make_client("192.0.2.10, not-an-ip")

    with pytest.raises(HTTPException) as caught:
        await api_auth.verify_client_request(
            make_request(),
            FakeDB(client),
            client_ip="192.0.2.10",
        )

    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_client_api_loopback_remains_allowed_by_documented_contract(monkeypatch):
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)
    client = make_client("192.0.2.10")

    result = await api_auth.verify_client_request(
        make_request(),
        FakeDB(client),
        client_ip="127.0.0.1",
    )

    assert result is client


@pytest.mark.asyncio
async def test_client_api_unknown_ip_is_rejected_when_allowlist_is_configured(monkeypatch):
    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)
    client = make_client("192.0.2.10")

    with pytest.raises(HTTPException) as caught:
        await api_auth.verify_client_request(
            make_request(),
            FakeDB(client),
            client_ip="unknown",
        )

    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_client_products_route_passes_trusted_resolved_ip_to_auth(monkeypatch):
    client = SimpleNamespace(id=17, user_id=None, company_name="CI client")
    captured = {}

    async def verify(request, db, **kwargs):
        captured["client_ip"] = kwargs.get("client_ip")
        return client

    class EmptyRows:
        def scalars(self):
            return self

        def all(self):
            return []

        def first(self):
            return None

    class EmptyDB:
        async def execute(self, statement):
            return EmptyRows()

    class BackgroundTasks:
        def add_task(self, *args, **kwargs):
            pass

    monkeypatch.setattr(api_auth, "verify_signature", lambda **kwargs: True)
    from app.api_v1.external import client_api
    monkeypatch.setattr(client_api, "verify_client_request", verify)
    monkeypatch.setattr(client_api, "get_client_ip", lambda request: "198.51.100.44")

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/client_products"),
        headers={"user-agent": "isolated-test-agent"},
    )
    await client_api.get_client_products(
        request=request,
        background_tasks=BackgroundTasks(),
        api_request=client_api.ClientProductsRequest(
            client_id=17,
            req_time=int(datetime.now(timezone.utc).timestamp()),
            sign="isolated-signature",
        ),
        db=EmptyDB(),
    )

    assert captured["client_ip"] == "198.51.100.44"
