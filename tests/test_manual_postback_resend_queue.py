"""人工补发必须通过统一队列，并与 PII 清理/自动重试互斥。"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import mysql

from app.core.postback.forwarder import FORWARD_QUEUE_REBUILD_MARKER
from app.services.cpl.postback_forward_log_service import PostbackForwardLogService


class _Scalars:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalars(self):
        return _Scalars(self.value)


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []
        self.added = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.results.pop(0))

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            value.id = 901


@pytest.mark.asyncio
async def test_manual_resend_enqueues_exact_target_without_copying_pii(monkeypatch):
    log = SimpleNamespace(
        id=11,
        conversion_id=22,
        publisher_id=33,
        product_id=None,
        pii_scrubbed_at=None,
        downstream_url=(
            "https://publisher.example/postback?click_id=private-click"
            "&ip=203.0.113.20&email=buyer@example.invalid"
        ),
        request_method="POST",
    )
    conversion = SimpleNamespace(id=22)
    db = _FakeDB([log, conversion, None])
    locked = []

    async def lock_conversion(session, conversion_id):
        locked.append((session, conversion_id))
        return True

    monkeypatch.setattr(
        "app.services.cpl.postback_forward_log_service._lock_conversion_for_queue_enqueue",
        lock_conversion,
    )

    response = await PostbackForwardLogService().resend_forward(
        forward_log_id=11,
        db=db,
        current_user=SimpleNamespace(id=7),
    )

    assert len(db.added) == 1
    task = db.added[0]
    assert task.conversion_id == 22
    assert task.publisher_id == 33
    assert task.product_id is None
    assert task.request_method == "POST"
    assert task.downstream_url == FORWARD_QUEUE_REBUILD_MARKER
    assert "private-click" not in task.downstream_url
    assert "203.0.113.20" not in task.downstream_url
    assert "buyer@example.invalid" not in task.downstream_url
    assert task.request_data is None
    assert task.request_params is None
    assert task.retry_count == 0
    assert task.next_retry_time is not None
    assert locked == [(db, 22)]
    assert response.data["queued"] is True

    # 原日志先以锁定读读取，目标队列去重也必须是锁定读。
    first_sql = str(db.statements[0].compile(dialect=mysql.dialect())).upper()
    last_sql = str(db.statements[-1].compile(dialect=mysql.dialect())).upper()
    assert "FOR UPDATE" in first_sql
    assert "FOR UPDATE" in last_sql


@pytest.mark.asyncio
async def test_manual_resend_rejects_scrubbed_log_before_conversion_lookup(monkeypatch):
    log = SimpleNamespace(
        id=11,
        conversion_id=22,
        publisher_id=33,
        product_id=None,
        pii_scrubbed_at=datetime(2026, 11, 1),
    )
    db = _FakeDB([log])

    async def unexpected_lock(*args, **kwargs):
        raise AssertionError("scrubbed log must not reach queue locking")

    monkeypatch.setattr(
        "app.services.cpl.postback_forward_log_service._lock_conversion_for_queue_enqueue",
        unexpected_lock,
    )

    with pytest.raises(HTTPException) as exc:
        await PostbackForwardLogService().resend_forward(
            forward_log_id=11,
            db=db,
            current_user=SimpleNamespace(id=7),
        )

    assert exc.value.status_code == 200
    assert exc.value.detail['code'] == 409
    assert not db.added
    assert len(db.statements) == 1


@pytest.mark.asyncio
async def test_manual_resend_rejects_successful_log_before_conversion_lookup(monkeypatch):
    log = SimpleNamespace(
        id=11,
        conversion_id=22,
        publisher_id=33,
        product_id=None,
        pii_scrubbed_at=None,
        success=True,
    )
    db = _FakeDB([log])

    with pytest.raises(HTTPException) as exc:
        await PostbackForwardLogService().resend_forward(
            forward_log_id=11,
            db=db,
            current_user=SimpleNamespace(id=7),
        )

    assert exc.value.status_code == 200
    assert exc.value.detail["code"] == 409
    assert not db.added
    # 成功状态在转换读取和入队前被拒绝。
    assert len(db.statements) == 1


@pytest.mark.asyncio
async def test_manual_resend_rejects_existing_target_queue_task(monkeypatch):
    log = SimpleNamespace(
        id=11,
        conversion_id=22,
        publisher_id=None,
        product_id=44,
        pii_scrubbed_at=None,
        downstream_url="https://product.example/postback",
        request_method="GET",
    )
    conversion = SimpleNamespace(id=22)
    existing_task = SimpleNamespace(id=55)
    db = _FakeDB([log, conversion, existing_task])

    async def lock_conversion(session, conversion_id):
        return True

    monkeypatch.setattr(
        "app.services.cpl.postback_forward_log_service._lock_conversion_for_queue_enqueue",
        lock_conversion,
    )

    with pytest.raises(HTTPException) as exc:
        await PostbackForwardLogService().resend_forward(
            forward_log_id=11,
            db=db,
            current_user=SimpleNamespace(id=7),
        )

    assert exc.value.status_code == 200
    assert exc.value.detail['code'] == 409
    assert not db.added
