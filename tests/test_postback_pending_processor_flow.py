"""非白名单 Postback 处理器必须进入待审批分支且不走正式转化。"""
import pytest
from fastapi import HTTPException

from app.services.cpl.postback_receive_service import raise_if_postback_retryable
from app.core.postback.processor import PostbackProcessor
from app.services.cpl import postback_pending_ingest_service


class _Result:
    def scalars(self):
        return self

    def first(self):
        return None


class _FakeDB:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _statement):
        return _Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_ip_failure_queues_pending_record_and_commits(monkeypatch):
    db = _FakeDB()
    captured = {}

    async def enqueue(**kwargs):
        captured.update(kwargs)
        return {"queued": True, "pending_id": 501}

    monkeypatch.setattr(
        postback_pending_ingest_service.pending_postback_ingest_service,
        "enqueue",
        enqueue,
    )

    result = await PostbackProcessor._handle_ip_failure(
        "partner_a",
        {"conversion_id": "c1", "payout": "1.00"},
        db,
        request_ip="203.0.113.10",
    )

    assert result["success"] is True
    assert result["is_pending"] is True
    assert result["pending_id"] == 501
    assert captured["request_ip"] == "203.0.113.10"
    assert db.commits == 1
    assert db.rollbacks == 0


@pytest.mark.asyncio
async def test_pending_queue_outage_returns_retryable_failure(monkeypatch):
    db = _FakeDB()

    async def unavailable(**_kwargs):
        raise postback_pending_ingest_service.PendingPostbackQueueError()

    monkeypatch.setattr(
        postback_pending_ingest_service.pending_postback_ingest_service,
        "enqueue",
        unavailable,
    )

    result = await PostbackProcessor._handle_ip_failure(
        "partner_a",
        {"conversion_id": "c1", "payout": "1.00"},
        db,
        request_ip="203.0.113.10",
    )

    assert result["success"] is False
    assert result["retryable"] is True
    assert db.rollbacks == 1
    assert db.commits == 0


@pytest.mark.asyncio
async def test_full_pending_queue_returns_retryable_failure(monkeypatch):
    db = _FakeDB()

    async def backlog_full(**_kwargs):
        return {"queued": False, "reason": "queue_backlog_full"}

    monkeypatch.setattr(
        postback_pending_ingest_service.pending_postback_ingest_service,
        "enqueue",
        backlog_full,
    )

    result = await PostbackProcessor._handle_ip_failure(
        "partner_a",
        {"conversion_id": "c1", "payout": "1.00"},
        db,
        request_ip="203.0.113.10",
    )

    assert result["success"] is False
    assert result["retryable"] is True
    assert db.rollbacks == 1
    assert db.commits == 0



@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    ["rate_limited", "missing_source_ip", "invalid_source_ip"],
)
async def test_rate_limit_and_untrusted_source_ip_are_retryable(
    monkeypatch, reason
):
    db = _FakeDB()

    async def rejected(**_kwargs):
        return {"queued": False, "reason": reason}

    monkeypatch.setattr(
        postback_pending_ingest_service.pending_postback_ingest_service,
        "enqueue",
        rejected,
    )

    result = await PostbackProcessor._handle_ip_failure(
        "partner_a",
        {"conversion_id": "c1", "payout": "1.00"},
        db,
        request_ip="203.0.113.10",
    )

    assert result["success"] is False
    assert result["retryable"] is True
    assert db.rollbacks == 1
    assert db.commits == 0

    with pytest.raises(HTTPException) as exc_info:
        raise_if_postback_retryable(result)
    assert exc_info.value.status_code == 503
