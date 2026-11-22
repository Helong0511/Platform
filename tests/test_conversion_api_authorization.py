"""CPL 转化与 Postback 路由的真实 FastAPI 权限矩阵回归测试。"""
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api_v1.cpl.conversions import summary as conversion_summary_routes
from app.api_v1.cpl.conversions.summary import router as conversion_summary_router
from app.api_v1.postback.routes.conversions import router as postback_conversion_router
from app.core.database import get_db, get_db_readonly
from app.core.security import (
    get_current_user,
    require_admin,
    require_publisher_or_admin,
)
from app.models.models import UserRole
from app.services.cpl.conversion_service import (
    _sanitize_by_offer_stats_for_client,
    _sanitize_conversion_summary_for_client,
)


class _Rows:
    def __init__(self, values=None, scalar=None):
        self.values = list(values or [])
        self.scalar_value = scalar

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        return self.scalar_value


class _AuthorizationDB:
    def __init__(self, *, client_ids=None, publisher_id=901):
        self.client_ids = list(client_ids or [])
        self.publisher_id = publisher_id
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _Rows(values=self.client_ids)
        return _Rows(scalar=self.publisher_id)


class _ConversionService:
    def __init__(self):
        self.summary_calls = []
        self.by_offer_calls = []

    async def get_conversion_summary(self, **kwargs):
        self.summary_calls.append(kwargs)
        return {
            "total_clicks": 12,
            "total_conversions": 3,
            "cr": 25.0,
            "total_po_after_discount": 300.0,
            "stats_list": [
                {
                    "offer_id": 10,
                    "publisher_id": 22,
                    "revenue": 300.0,
                }
            ],
        }

    async def get_conversions_by_offer(self, **kwargs):
        self.by_offer_calls.append(kwargs)
        return [{"offer_id": 10, "offer_name": "scoped-offer", "click_count": 12}]


def _build_summary_app(*, user=None, db=None, service=None, authenticated=True, monkeypatch):
    app = FastAPI()
    app.include_router(conversion_summary_router, prefix="/conversion-summary")
    db = db or _AuthorizationDB()
    service = service or _ConversionService()

    async def override_db():
        yield db

    async def override_service(_db):
        return service

    # 路由函数内部直接调用 get_conversion_service(db)，不是 Depends；需替换模块级工厂。
    monkeypatch.setattr(conversion_summary_routes, "get_conversion_service", override_service)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_db_readonly] = override_db
    if authenticated:
        async def override_current_user():
            return user

        app.dependency_overrides[get_current_user] = override_current_user
    return app, db, service


async def _get(app, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test.local",
    ) as client:
        return await client.get(path)


def test_conversion_summary_routes_keep_publisher_or_admin_dependency():
    routes = [
        route for route in conversion_summary_router.routes
        if isinstance(route, APIRoute)
    ]
    assert {route.path for route in routes} == {"/", "/by-offer"}
    for route in routes:
        assert any(
            dependency.call is require_publisher_or_admin
            for dependency in route.dependant.dependencies
        )


def test_postback_conversion_routes_keep_admin_only_dependency():
    routes = [
        route for route in postback_conversion_router.routes
        if isinstance(route, APIRoute)
    ]
    assert {route.path for route in routes} == {
        "/postback/conversions",
        "/postback/stats",
        "/postback/conversions/{conversion_id}/status",
        "/postback/check-duplicates",
    }
    for route in routes:
        assert any(
            dependency.call is require_admin
            for dependency in route.dependant.dependencies
        )


@pytest.mark.asyncio
async def test_conversion_summary_rejects_unauthenticated_request(monkeypatch):
    app, _, _ = _build_summary_app(authenticated=False, monkeypatch=monkeypatch)

    response = await _get(app, "/conversion-summary/")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_conversion_summary_allows_admin_without_client_lookup(monkeypatch):
    user = SimpleNamespace(id=1, role=UserRole.ADMIN)
    db = _AuthorizationDB()
    service = _ConversionService()
    app, db, service = _build_summary_app(user=user, db=db, service=service, monkeypatch=monkeypatch)

    response = await _get(app, "/conversion-summary/")

    assert response.status_code == 200
    assert response.json()["code"] == 200
    assert response.json()["data"]["total_clicks"] == 12
    assert db.statements == []
    assert service.summary_calls[0]["current_user"] is user


@pytest.mark.asyncio
async def test_conversion_summary_allows_client_with_active_publisher_scope(monkeypatch):
    user = SimpleNamespace(id=77, role=UserRole.CLIENT)
    db = _AuthorizationDB(client_ids=[11, 22], publisher_id=901)
    service = _ConversionService()
    app, db, service = _build_summary_app(user=user, db=db, service=service, monkeypatch=monkeypatch)

    response = await _get(app, "/conversion-summary/?publisher_id=901")

    assert response.status_code == 200
    assert response.json()["data"]["total_clicks"] == 12
    assert len(db.statements) == 2
    assert service.summary_calls[0]["current_user"] is user
    assert service.summary_calls[0]["publisher_id"] == 901


@pytest.mark.asyncio
async def test_conversion_summary_rejects_client_without_active_client_record(monkeypatch):
    user = SimpleNamespace(id=78, role=UserRole.CLIENT)
    db = _AuthorizationDB(client_ids=[], publisher_id=None)
    service = _ConversionService()
    app, db, service = _build_summary_app(user=user, db=db, service=service, monkeypatch=monkeypatch)

    response = await _get(app, "/conversion-summary/")

    assert response.status_code == 403
    assert len(db.statements) == 1
    assert service.summary_calls == []


@pytest.mark.asyncio
async def test_conversion_summary_rejects_client_without_active_publisher(monkeypatch):
    user = SimpleNamespace(id=79, role=UserRole.CLIENT)
    db = _AuthorizationDB(client_ids=[11, 22], publisher_id=None)
    service = _ConversionService()
    app, db, service = _build_summary_app(user=user, db=db, service=service, monkeypatch=monkeypatch)

    response = await _get(app, "/conversion-summary/")

    assert response.status_code == 403
    assert len(db.statements) == 2
    assert service.summary_calls == []


@pytest.mark.parametrize("role", ["publisher", "advertiser", "readonly", "operator"])
@pytest.mark.asyncio
async def test_conversion_summary_rejects_non_client_non_admin_roles(role, monkeypatch):
    user = SimpleNamespace(id=80, role=role)
    db = _AuthorizationDB()
    service = _ConversionService()
    app, db, service = _build_summary_app(user=user, db=db, service=service, monkeypatch=monkeypatch)

    response = await _get(app, "/conversion-summary/")

    assert response.status_code == 403
    assert db.statements == []
    assert service.summary_calls == []


@pytest.mark.asyncio
async def test_conversion_by_offer_client_route_uses_same_scope_dependency(monkeypatch):
    user = SimpleNamespace(id=81, role=UserRole.CLIENT)
    db = _AuthorizationDB(client_ids=[11], publisher_id=902)
    service = _ConversionService()
    app, db, service = _build_summary_app(user=user, db=db, service=service, monkeypatch=monkeypatch)

    response = await _get(app, "/conversion-summary/by-offer")

    assert response.status_code == 200
    assert response.json()["data"][0]["offer_id"] == 10
    assert service.by_offer_calls[0]["current_user"] is user


@pytest.mark.asyncio
async def test_postback_conversion_api_rejects_client_role_before_handler(monkeypatch):
    from app.api_v1.postback.routes import conversions as postback_routes

    user = SimpleNamespace(id=82, role=UserRole.CLIENT)
    db = _AuthorizationDB()
    app = FastAPI()
    app.include_router(postback_conversion_router)

    async def override_current_user():
        return user

    async def override_db():
        yield db

    async def forbidden_handler(*args, **kwargs):
        raise AssertionError("管理员专属 Postback handler 不应被非管理员调用")

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(
        postback_routes.conversion_handler,
        "get_postback_conversions",
        forbidden_handler,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test.local",
    ) as client:
        response = await client.get("/postback/conversions")

    assert response.status_code == 403


def test_client_response_sanitizers_remove_upstream_financial_and_advertiser_fields():
    summary = _sanitize_conversion_summary_for_client(
        {
            "total_clicks": 10,
            "total_conversions": 2,
            "total_po": 999.0,
            "total_po_after_discount": 300.0,
            "total_profit": 699.0,
            "stats_list": [
                {
                    "offer_id": 10,
                    "publisher_id": 22,
                    "po": 999.0,
                    "pub_po": 300.0,
                    "adv_po": 999.0,
                    "advertiser_id": 7,
                    "advertiser_name": "upstream-private",
                }
            ],
        }
    )

    assert "total_po" not in summary
    assert "total_profit" not in summary
    assert summary["total_po_after_discount"] == 300.0
    stats = summary["stats_list"][0]
    assert "po" not in stats
    assert "adv_po" not in stats
    assert "advertiser_id" not in stats
    assert "advertiser_name" not in stats
    assert stats["pub_po"] == 300.0


def test_client_by_offer_sanitizer_removes_upstream_po():
    result = _sanitize_by_offer_stats_for_client(
        [{"offer_id": 10, "click_count": 8, "po": 500.0}]
    )

    assert result == [{"offer_id": 10, "click_count": 8}]
