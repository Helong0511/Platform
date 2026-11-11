"""权限缓存新鲜度测试：账号禁用/限制登录必须以本次数据库读取为准。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core import permission_cache, security
from app.models.models import UserRole


def _request():
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/private",
            "raw_path": b"/api/v1/private",
            "query_string": b"",
            "headers": [(b"host", b"platform.example.invalid")],
            "client": ("127.0.0.1", 54321),
            "server": ("127.0.0.1", 443),
        }
    )


class _ScalarResult:
    def __init__(self, user):
        self.user = user

    def scalars(self):
        return self

    def first(self):
        return self.user


class _DB:
    def __init__(self, user):
        self.user = user
        self.queries = 0

    async def execute(self, statement):
        self.queries += 1
        return _ScalarResult(self.user)


@pytest.mark.asyncio
async def test_stale_permission_cache_cannot_keep_disabled_user_authenticated(monkeypatch):
    user = SimpleNamespace(
        id=51,
        role=UserRole.ADMIN,
        is_active=False,
        login_restricted=False,
        login_message=None,
    )
    db = _DB(user)

    async def valid_token(token, db=None):
        return {"sub": "51", "type": "access"}

    async def unexpected_cache_access(user_id, db):
        raise AssertionError("认证流程不得依赖可能过期的权限缓存")

    monkeypatch.setattr(security.JWTUtils, "verify_token", valid_token)
    monkeypatch.setattr(permission_cache, "get_user_permissions", unexpected_cache_access)

    with pytest.raises(HTTPException) as exc:
        await security.get_current_user(_request(), db, "synthetic-access-token")

    assert exc.value.status_code == 403
    assert db.queries == 1


@pytest.mark.asyncio
async def test_stale_permission_cache_cannot_keep_login_restricted_user_authenticated(monkeypatch):
    user = SimpleNamespace(
        id=52,
        role=UserRole.CLIENT,
        is_active=True,
        login_restricted=True,
        login_message="管理员限制登录",
    )
    db = _DB(user)

    async def valid_token(token, db=None):
        return {"sub": "52", "type": "access"}

    async def unexpected_cache_access(user_id, db):
        raise AssertionError("认证流程不得依赖可能过期的权限缓存")

    monkeypatch.setattr(security.JWTUtils, "verify_token", valid_token)
    monkeypatch.setattr(permission_cache, "get_user_permissions", unexpected_cache_access)

    with pytest.raises(HTTPException) as exc:
        await security.get_current_user(_request(), db, "synthetic-access-token")

    assert exc.value.status_code == 403
    assert db.queries == 1



@pytest.mark.asyncio
async def test_active_user_is_not_blocked_by_stale_disabled_permission_cache(monkeypatch):
    user = SimpleNamespace(
        id=53,
        role=UserRole.CLIENT,
        is_active=True,
        login_restricted=False,
        login_message=None,
    )
    db = _DB(user)

    async def valid_token(token, db=None):
        return {"sub": "53", "type": "access"}

    async def unexpected_cache_access(user_id, db):
        raise AssertionError("认证流程应以数据库当前状态为准，不读取旧缓存")

    monkeypatch.setattr(security.JWTUtils, "verify_token", valid_token)
    monkeypatch.setattr(permission_cache, "get_user_permissions", unexpected_cache_access)

    result = await security.get_current_user(_request(), db, "synthetic-access-token")

    assert result is user
    assert db.queries == 1
