"""Pending 审批必须识别已提交的 Postback 事件收据。"""
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql

from app.services.cpl.postback_pending_service import PostbackPendingService


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, value):
        self.value = value
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _ScalarResult(self.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(("receipt_id", "expected"), [(17, True), (None, False)])
async def test_pending_event_receipt_guard_checks_canonical_identity(receipt_id, expected):
    pending = SimpleNamespace(
        platform="partner_a",
        conversion_id="conversion-123",
        event_name=" ",
    )
    db = _FakeDB(receipt_id)

    result = await PostbackPendingService()._pending_event_receipt_exists(pending, db)

    assert result is expected
    assert pending.event_name == "default"
    compiled = str(db.statement.compile(dialect=mysql.dialect()))
    assert "postback_event_receipts" in compiled
    assert "platform" in compiled
    assert "conversion_id" in compiled
    assert "event_name" in compiled
    assert "FOR UPDATE" in compiled.upper()
