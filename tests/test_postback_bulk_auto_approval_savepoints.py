"""IP 白名单批量自动审批的 SAVEPOINT 事务边界测试。"""
from types import SimpleNamespace

import pytest

from app.services.cpl import postback_pending_service as service_module


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeNested:
    def __init__(self, db):
        self.db = db
        self.snapshot = None

    async def __aenter__(self):
        self.snapshot = [
            (row.status, row.approved_at, row.rejected_at)
            for row in self.db.pending
        ]
        self.event_count = len(self.db.events)
        return self

    async def __aexit__(self, exc_type, _exc, _tb):
        if exc_type is not None:
            for row, state in zip(self.db.pending, self.snapshot):
                row.status, row.approved_at, row.rejected_at = state
            del self.db.events[self.event_count:]
            return False
        return False


class _FakeDB:
    def __init__(self, pending, fail_pending_id=None, invalidate_on_failure=False):
        self.pending = pending
        self.fail_pending_id = fail_pending_id
        self.invalidate_on_failure = invalidate_on_failure
        self.current_pending_id = None
        self.events = []
        self.rollback_count = 0
        self.is_active = True

    async def execute(self, _statement):
        return _ScalarRows(self.pending)

    def begin_nested(self):
        return _FakeNested(self)

    async def flush(self):
        if self.current_pending_id == self.fail_pending_id:
            if self.invalidate_on_failure:
                self.is_active = False
            raise RuntimeError("simulated constraint failure")

    async def rollback(self):
        self.rollback_count += 1
        self.is_active = True
        for row in self.pending:
            row.status = "pending"
            row.approved_at = None
            row.rejected_at = None
        self.events.clear()


def _pending(row_id):
    return SimpleNamespace(
        id=row_id,
        status="pending",
        approved_at=None,
        rejected_at=None,
        request_ip="203.0.113.20",
    )


@pytest.mark.asyncio
async def test_bulk_auto_approval_rolls_back_only_failed_row(monkeypatch):
    rows = [_pending(1), _pending(2), _pending(3)]
    db = _FakeDB(rows, fail_pending_id=2)
    service = service_module.PostbackPendingService()

    async def no_existing(_pending, _db):
        _db.current_pending_id = _pending.id
        return None

    async def create_conversion(pending, _db):
        pending.status = "approved"
        pending.approved_at = "approved-at"
        return SimpleNamespace(id=1000 + pending.id)

    def add_audit(session, **kwargs):
        session.events.append(kwargs)

    monkeypatch.setattr(service, "_pending_conversion_exists", no_existing)
    monkeypatch.setattr(service, "_create_conversion_from_pending", create_conversion)
    monkeypatch.setattr(service_module, "add_postback_approval_audit", add_audit)

    result = await service.auto_approve_pending_by_ip(
        "203.0.113.20", db, SimpleNamespace(id=7, username="admin")
    )

    assert result == {
        "approved_count": 2,
        "skipped_count": 0,
        "failed_count": 1,
        "approved_ids": [1, 3],
    }
    assert [row.status for row in rows] == ["approved", "pending", "approved"]
    assert [event["pending_conversion_id"] for event in db.events] == [1, 3]


@pytest.mark.asyncio
async def test_bulk_auto_approval_clears_success_counts_if_outer_transaction_fails(monkeypatch):
    rows = [_pending(1), _pending(2)]
    db = _FakeDB(rows, fail_pending_id=2, invalidate_on_failure=True)
    service = service_module.PostbackPendingService()

    async def no_existing(_pending, _db):
        _db.current_pending_id = _pending.id
        return None

    async def create_conversion(pending, _db):
        pending.status = "approved"
        return SimpleNamespace(id=1000 + pending.id)

    monkeypatch.setattr(service, "_pending_conversion_exists", no_existing)
    monkeypatch.setattr(service, "_create_conversion_from_pending", create_conversion)
    monkeypatch.setattr(
        service_module,
        "add_postback_approval_audit",
        lambda *_args, **_kwargs: None,
    )

    result = await service.auto_approve_pending_by_ip(
        "203.0.113.20", db, SimpleNamespace(id=7, username="admin")
    )

    assert result == {
        "approved_count": 0,
        "skipped_count": 0,
        "failed_count": 2,
        "approved_ids": [],
    }
    assert db.rollback_count == 1
    assert [row.status for row in rows] == ["pending", "pending"]
