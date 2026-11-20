"""Web/IP 白名单审批路径必须在业务事务中记录审计事件。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.cpl.postback_pending_service import PostbackPendingService


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value


class _FakeAsyncDB:
    def __init__(self, result):
        self.result = result
        self.events = []
        self.bind = object()
        self.flush_count = 0
        self.rollback_count = 0

    async def execute(self, _statement):
        return self.result

    def add(self, event):
        self.events.append(event)

    async def flush(self):
        self.flush_count += 1

    async def refresh(self, _value):
        return None

    async def rollback(self):
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_ip_whitelist_auto_approval_audits_existing_duplicate(monkeypatch):
    service = PostbackPendingService()
    pending = SimpleNamespace(id=10, status="pending", approved_at=None)
    db = _FakeAsyncDB(_ScalarResult([pending]))

    async def exists(_pending, _db):
        return True

    monkeypatch.setattr(service, "_pending_conversion_exists", exists)
    result = await service.auto_approve_pending_by_ip(
        "203.0.113.10",
        db,
        SimpleNamespace(id=42, username="admin"),
    )

    assert result["skipped_count"] == 1
    assert pending.status == "approved"
    event = db.events[0]
    assert event.actor_type == "system_user"
    assert event.actor_id == "42"
    assert event.source == "ip_whitelist"
    assert event.action == "auto_approve"
    assert event.outcome == "already_exists"
    assert event.previous_status == "pending"
    assert event.new_status == "approved"


@pytest.mark.asyncio
async def test_ip_whitelist_auto_approval_audits_new_conversion(monkeypatch):
    service = PostbackPendingService()
    pending = SimpleNamespace(id=11, status="pending", approved_at=None)
    db = _FakeAsyncDB(_ScalarResult([pending]))

    async def exists(_pending, _db):
        return False

    async def create(_pending, _db):
        _pending.status = "approved"
        _pending.approved_at = object()
        return SimpleNamespace(id=700)

    monkeypatch.setattr(service, "_pending_conversion_exists", exists)
    monkeypatch.setattr(service, "_create_conversion_from_pending", create)

    result = await service.auto_approve_pending_by_ip(
        "203.0.113.11",
        db,
        SimpleNamespace(id=43, username="admin"),
    )

    assert result["approved_count"] == 1
    event = db.events[0]
    assert event.actor_id == "43"
    assert event.action == "auto_approve"
    assert event.outcome == "approved"
    assert event.pending_conversion_id == 11


@pytest.mark.asyncio
async def test_web_duplicate_approval_attempt_is_persisted_separately(monkeypatch):
    service = PostbackPendingService()
    pending = SimpleNamespace(id=12, status="pending")
    db = _FakeAsyncDB(_ScalarResult(pending))
    captured = {}

    async def exists(_pending, _db):
        return True

    async def persist(bind, **fields):
        captured["bind"] = bind
        captured.update(fields)

    monkeypatch.setattr(service, "_pending_conversion_exists", exists)
    monkeypatch.setattr(
        "app.services.cpl.postback_pending_service.persist_postback_approval_audit_independently",
        persist,
    )

    with pytest.raises(HTTPException):
        await service.approve_pending_conversion(
            12,
            db,
            SimpleNamespace(id=44, username="admin"),
        )

    assert captured["actor_type"] == "system_user"
    assert captured["actor_id"] == 44
    assert captured["source"] == "web"
    assert captured["action"] == "approve"
    assert captured["outcome"] == "already_exists"
    assert captured["pending_conversion_id"] == 12



@pytest.mark.asyncio
async def test_web_rejection_audit_is_added_to_same_session_transaction():
    service = PostbackPendingService()
    pending = SimpleNamespace(id=13, status="pending", rejected_at=None)
    db = _FakeAsyncDB(_ScalarResult(pending))

    response = await service.reject_pending_conversion(
        13,
        db,
        SimpleNamespace(id=45, username="admin"),
    )

    assert response is not None
    assert pending.status == "rejected"
    assert db.flush_count == 1
    event = db.events[0]
    assert event.actor_type == "system_user"
    assert event.actor_id == "45"
    assert event.source == "web"
    assert event.action == "reject"
    assert event.outcome == "rejected"
    assert event.previous_status == "pending"
    assert event.new_status == "rejected"



@pytest.mark.asyncio
async def test_web_successful_approval_audit_is_added_before_request_commit(monkeypatch):
    import importlib

    service_module = importlib.import_module(
        "app.services.cpl.postback_pending_service"
    )
    service = service_module.PostbackPendingService()
    pending = SimpleNamespace(id=14, status="pending", approved_at=None)
    db = _FakeAsyncDB(_ScalarResult(pending))

    async def exists(_pending, _db):
        return False

    async def create(_pending, _db):
        _pending.status = "approved"
        _pending.approved_at = object()
        return SimpleNamespace(id=701)

    monkeypatch.setattr(service, "_pending_conversion_exists", exists)
    monkeypatch.setattr(service, "_create_conversion_from_pending", create)
    monkeypatch.setattr(
        service_module.PostbackConversionResponse,
        "model_validate",
        classmethod(lambda _cls, _conversion: object()),
    )
    monkeypatch.setattr(
        service_module.ResponseBaseSchema,
        "success",
        staticmethod(lambda **kwargs: kwargs),
    )

    response = await service.approve_pending_conversion(
        14,
        db,
        SimpleNamespace(id=46, username="admin"),
    )

    assert response["message"] == "已批准并创建转化记录"
    assert pending.status == "approved"
    assert db.flush_count == 1
    event = db.events[0]
    assert event.actor_type == "system_user"
    assert event.actor_id == "46"
    assert event.source == "web"
    assert event.action == "approve"
    assert event.outcome == "approved"
    assert event.pending_conversion_id == 14
    assert event.conversion_id == 701
