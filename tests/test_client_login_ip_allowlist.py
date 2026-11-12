"""客户登录与刷新令牌必须遵守统一的来源 IP 白名单规则。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api_v1.auth import auth as auth_api
from app.api_v1.auth import refresh as refresh_api
from app.models.models import UserRole
from app.core.api_auth import _is_user_client_ip_allowed
from app.schemas.auth import RefreshTokenRequest


def _request():
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "query_string": b"",
            "headers": [(b"host", b"platform.example.invalid")],
            "client": ("127.0.0.1", 54321),
            "server": ("127.0.0.1", 443),
        }
    )


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value


class _DB:
    def __init__(self, user):
        self.user = user
        self.rollback_called = False

    async def execute(self, statement):
        return _ScalarResult(self.user)

    async def rollback(self):
        self.rollback_called = True


def _client_user():
    client = SimpleNamespace(allowed_ips="192.0.2.10")
    user = SimpleNamespace(
        id=91,
        username="synthetic-client",
        role=UserRole.CLIENT,
        is_active=True,
        login_restricted=False,
        login_message=None,
        clients=[SimpleNamespace(allowed_ips=""), client],
        verify_password=lambda password: password == "synthetic-password",
    )
    return user, client


@pytest.mark.asyncio
async def test_client_login_does_not_implicitly_allow_loopback(monkeypatch):
    user, client = _client_user()
    db = _DB(user)

    monkeypatch.setattr(auth_api, "get_client_ip", lambda request: "127.0.0.1")
    monkeypatch.setattr(
        auth_api,
        "get_first_loaded_collection_item",
        lambda user, relationship: user.clients[0],
    )

    async def record_failure(*args, **kwargs):
        return None

    monkeypatch.setattr(auth_api, "_record_login_failure", record_failure)

    with pytest.raises(HTTPException) as exc:
        await auth_api.login(
            _request(),
            db,
            SimpleNamespace(username=user.username, password="synthetic-password"),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token_cannot_bypass_client_loopback_allowlist(monkeypatch):
    user, client = _client_user()
    db = _DB(user)

    async def valid_refresh_token(token, db=None):
        return {"sub": str(user.id), "type": "refresh"}

    async def unexpected_revoke(*args, **kwargs):
        raise AssertionError("未授权 IP 不得轮换或撤销会话令牌")

    monkeypatch.setattr(refresh_api.JWTUtils, "verify_token", valid_refresh_token)
    monkeypatch.setattr(refresh_api, "get_client_ip", lambda request: "127.0.0.1")
    monkeypatch.setattr(
        refresh_api,
        "get_first_loaded_collection_item",
        lambda user, relationship: user.clients[0],
    )
    monkeypatch.setattr(refresh_api, "revoke_tokens_from_request", unexpected_revoke)

    with pytest.raises(HTTPException) as exc:
        await refresh_api.refresh_token(
            _request(),
            RefreshTokenRequest(refresh_token="synthetic-refresh-token"),
            db,
        )

    assert exc.value.status_code == 403
    assert db.rollback_called is True



def test_inactive_client_allowlist_does_not_restrict_shared_login():
    clients = [
        SimpleNamespace(is_active=False, allowed_ips="192.0.2.10"),
        SimpleNamespace(is_active=True, allowed_ips=""),
    ]

    assert _is_user_client_ip_allowed(clients, "127.0.0.1") is True


@pytest.mark.asyncio
async def test_client_login_rejects_account_without_active_client_membership(monkeypatch):
    user, _ = _client_user()
    user.clients = [SimpleNamespace(is_active=False, allowed_ips="")]
    db = _DB(user)

    monkeypatch.setattr(auth_api, "get_client_ip", lambda request: "127.0.0.1")

    async def record_failure(*args, **kwargs):
        return None

    monkeypatch.setattr(auth_api, "_record_login_failure", record_failure)

    with pytest.raises(HTTPException) as exc:
        await auth_api.login(
            _request(),
            db,
            SimpleNamespace(username=user.username, password="synthetic-password"),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_refresh_rejects_account_without_active_client_membership(monkeypatch):
    user, _ = _client_user()
    user.clients = [SimpleNamespace(is_active=False, allowed_ips="")]
    db = _DB(user)

    async def valid_refresh_token(token, db=None):
        return {"sub": str(user.id), "type": "refresh"}

    monkeypatch.setattr(refresh_api.JWTUtils, "verify_token", valid_refresh_token)

    with pytest.raises(HTTPException) as exc:
        await refresh_api.refresh_token(
            _request(),
            RefreshTokenRequest(refresh_token="synthetic-refresh-token"),
            db,
        )

    assert exc.value.status_code == 403
    assert db.rollback_called is True
