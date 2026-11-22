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


class _FakeNestedTransaction:
    """模拟 SQLAlchemy SAVEPOINT，异常时恢复当前保存点内的状态。"""

    def __init__(self, db):
        self.db = db
        self.snapshot = None

    async def __aenter__(self):
        self.snapshot = [
            (getattr(row, "status", None), getattr(row, "approved_at", None),
             getattr(row, "rejected_at", None))
            for row in self.db.pending_rows
        ]
        self.event_count = len(self.db.events)
        return self

    async def __aexit__(self, exc_type, _exc, _tb):
        if exc_type is not None:
            for row, state in zip(self.db.pending_rows, self.snapshot):
                if hasattr(row, "status"):
                    row.status = state[0]
                if hasattr(row, "approved_at"):
                    row.approved_at = state[1]
                if hasattr(row, "rejected_at"):
                    row.rejected_at = state[2]
            del self.db.events[self.event_count:]
        return False


class _FakeAsyncDB:
    def __init__(self, result):
        self.result = result
        self.events = []
        self.bind = object()
        self.flush_count = 0
        self.rollback_count = 0
        self.is_active = True
        self.pending_rows = []

    async def execute(self, _statement):
        rows = self.result.value if isinstance(self.result.value, list) else [self.result.value]
        self.pending_rows = [row for row in rows if row is not None]
        return self.result

    def begin_nested(self):
        return _FakeNestedTransaction(self)

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
        return 654

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
    assert event.conversion_id == 654
    assert event.previous_status == "pending"
    assert event.new_status == "approved"


@pytest.mark.asyncio
async def test_ip_whitelist_auto_approval_audits_new_conversion(monkeypatch):
    service = PostbackPendingService()
    pending = SimpleNamespace(id=11, status="pending", approved_at=None)
    db = _FakeAsyncDB(_ScalarResult([pending]))

    async def exists(_pending, _db):
        return None

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
    assert event.conversion_id == 700


@pytest.mark.asyncio
async def test_web_duplicate_approval_attempt_is_persisted_separately(monkeypatch):
    service = PostbackPendingService()
    pending = SimpleNamespace(id=12, status="pending")
    db = _FakeAsyncDB(_ScalarResult(pending))
    captured = {}

    async def exists(_pending, _db):
        return 655

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
    assert captured["conversion_id"] == 655
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
        return None

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


@pytest.mark.asyncio
@pytest.mark.parametrize("method,action", [
    ("approve_pending_conversion", "approve"),
    ("reject_pending_conversion", "reject"),
])
async def test_web_already_processed_attempt_is_audited_independently(
    monkeypatch, method, action
):
    service = PostbackPendingService()
    pending = SimpleNamespace(id=90, status="approved")
    db = _FakeAsyncDB(_ScalarResult(pending))
    captured = {}

    async def persist(bind, **fields):
        captured.update(fields)

    monkeypatch.setattr(
        "app.services.cpl.postback_pending_service.persist_postback_approval_audit_independently",
        persist,
    )

    with pytest.raises(HTTPException):
        await getattr(service, method)(
            90,
            db,
            SimpleNamespace(id=99, username="admin"),
        )

    assert captured["outcome"] == "already_processed"
    assert captured["action"] == action
    assert captured["previous_status"] == "approved"
    assert captured["new_status"] == "approved"
    assert captured["pending_conversion_id"] == 90
    assert db.events == []
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_manual_approval_sanitizes_pending_raw_data_before_promotion():
    service = PostbackPendingService()
    pending = SimpleNamespace(
        id=901,
        status="pending",
        platform="test-platform",
        conversion_id="conversion-901",
        event_name="install",
        event_value=None,
        original_payout=10,
        payout=9,
        devad_id=None,
        os="Android",
        carrier=None,
        ip="192.0.2.10",
        gid="202",
        product_id=5,
        client_id=6,
        click_id=None,
        click_time=None,
        raw_data='{"email":"private@example.com","click_id":"business-click-901"}',
    )
    db = _FakeAsyncDB(_ScalarResult(None))

    conversion = await service._create_conversion_from_pending(pending, db)

    assert conversion.raw_data is not None
    assert "private@example.com" not in conversion.raw_data
    assert "business-click-901" in conversion.raw_data
    assert pending.status == "approved"
