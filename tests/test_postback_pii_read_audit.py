"""Postback PII 查询成功后必须写入严格审计日志，且不得把原始标识写进筛选详情。"""
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api_v1.postback.routes import conversions as postback_routes
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import UserRole


class _AuditDB:
    pass


def _build_app(monkeypatch, *, commit_error=None):
    app = FastAPI()
    app.include_router(postback_routes.router)
    db = _AuditDB()
    user = SimpleNamespace(id=1, username="security-admin", role=UserRole.ADMIN)
    events = []
    audit_calls = []
    commit_calls = []

    async def override_user():
        return user

    async def override_db():
        yield db

    async def fake_log_user_action(**kwargs):
        events.append("audit")
        audit_calls.append(kwargs)

    async def fake_commit_audit_log(received_db):
        events.append("commit")
        commit_calls.append(received_db)
        if commit_error:
            raise commit_error

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(postback_routes, "log_user_action", fake_log_user_action)
    monkeypatch.setattr(postback_routes, "commit_audit_log", fake_commit_audit_log)
    return app, db, user, events, audit_calls, commit_calls


async def _request(app, path, *, raise_app_exceptions=True):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app,
            raise_app_exceptions=raise_app_exceptions,
        ),
        base_url="http://test.local",
    ) as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_postback_conversion_read_audit_records_filter_presence_not_raw_ids(monkeypatch):
    app, db, user, events, audit_calls, commit_calls = _build_app(monkeypatch)

    async def fake_handler(*args, **kwargs):
        events.append("handler")
        return {"ok": True, "data": []}

    monkeypatch.setattr(
        postback_routes.conversion_handler,
        "get_postback_conversions",
        fake_handler,
    )

    response = await _request(
        app,
        "/postback/conversions?click_id=raw-click-secret"
        "&conversion_or_click_id=raw-conversion-secret&page=2&page_size=100",
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert events == ["handler", "audit", "commit"]
    assert commit_calls == [db]
    assert len(audit_calls) == 1

    audit = audit_calls[0]
    assert audit["action_type"] == "API_ACCESS"
    assert audit["resource_type"] == "POSTBACK_PII_ACCESS"
    assert audit["resource_name"] == "conversion_list"
    assert audit["user"] is user
    assert audit["request_method"] == "GET"
    assert audit["request_path"] == "/postback/conversions"
    assert audit["status_code"] == 200
    assert audit["success"] is True
    assert audit["strict"] is True
    assert audit["details"]["page"] == 2
    assert audit["details"]["page_size"] == 100
    assert set(audit["details"]["filter_fields_present"]) >= {
        "click_id",
        "conversion_or_click_id",
    }
    assert "raw-click-secret" not in str(audit)
    assert "raw-conversion-secret" not in str(audit)


@pytest.mark.asyncio
async def test_postback_stats_and_duplicate_reads_are_also_audited(monkeypatch):
    app, db, _, events, audit_calls, commit_calls = _build_app(monkeypatch)

    async def fake_stats(*args, **kwargs):
        events.append("stats_handler")
        return {"ok": True, "data": []}

    async def fake_duplicates(*args, **kwargs):
        events.append("duplicate_handler")
        return {"ok": True, "data": {"summary": {}}}

    monkeypatch.setattr(postback_routes.stats_handler, "get_postback_stats", fake_stats)
    monkeypatch.setattr(
        postback_routes.duplicate_handler,
        "check_duplicate_conversions",
        fake_duplicates,
    )

    stats_response = await _request(app, "/postback/stats?platform=network-a")
    duplicate_response = await _request(
        app,
        "/postback/check-duplicates?conversion_id=raw-transaction-secret",
    )

    assert stats_response.status_code == 200
    assert duplicate_response.status_code == 200
    assert [call["resource_name"] for call in audit_calls] == [
        "conversion_stats",
        "duplicate_check",
    ]
    assert len(commit_calls) == 2
    assert commit_calls == [db, db]
    assert events == [
        "stats_handler", "audit", "commit",
        "duplicate_handler", "audit", "commit",
    ]
    assert "raw-transaction-secret" not in str(audit_calls[1])
    assert audit_calls[1]["details"]["filter_fields_present"] == ["conversion_id"]


@pytest.mark.asyncio
async def test_postback_pii_read_fails_closed_when_audit_commit_fails(monkeypatch):
    app, _, _, events, audit_calls, commit_calls = _build_app(
        monkeypatch,
        commit_error=RuntimeError("audit database unavailable"),
    )

    async def fake_handler(*args, **kwargs):
        events.append("handler")
        return {"ok": True, "data": [{"ip": "203.0.113.9"}]}

    monkeypatch.setattr(
        postback_routes.conversion_handler,
        "get_postback_conversions",
        fake_handler,
    )

    response = await _request(
        app,
        "/postback/conversions",
        raise_app_exceptions=False,
    )

    assert response.status_code == 500
    assert events == ["handler", "audit", "commit"]
    assert len(audit_calls) == 1
    assert len(commit_calls) == 1
