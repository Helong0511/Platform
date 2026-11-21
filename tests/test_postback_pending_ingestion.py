"""非白名单 Postback 待审批入队安全测试。"""
import json

import pytest

from app.services.cpl import postback_pending_ingest_service as ingest


class _ScalarResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, existing_id=None, pending_count=0, guard_available=True):
        self.existing_id = existing_id
        self.pending_count = pending_count
        self.guard_available = guard_available
        self.guard_statement = None
        self.added = []
        self.flush_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        if "postback_pending_queue_guard" in str(statement):
            self.guard_statement = statement
            return _ScalarResult(1 if self.guard_available else None)
        return _ScalarResult(self.existing_id)

    async def scalar(self, _statement):
        return self.pending_count

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flush_count += 1
        self.added[-1].id = 91

    async def rollback(self):
        self.rollback_count += 1


@pytest.fixture
def valid_payload():
    return {
        "conversion_id": "conv-2026-0001",
        "click_id": "click-123",
        "event_name": "Purchase",
        "payout": "12.3400",
        "email": "buyer@example.invalid",
        "phone": "+15555550123",
        "ip": "198.51.100.200",
        "user_agent": "private-agent",
        "devad_id": "device-ad-123",
    }


@pytest.mark.asyncio
async def test_valid_non_whitelisted_postback_is_sanitized_and_queued(
    monkeypatch, valid_payload
):
    db = _FakeDB()
    monkeypatch.setattr(
        ingest.PendingPostbackIngestService,
        "_allow_enqueue",
        staticmethod(_allow),
    )

    result = await ingest.PendingPostbackIngestService.enqueue(
        platform="partner_a",
        raw_data=valid_payload,
        request_ip="203.0.113.10",
        db=db,
    )

    assert result == {"queued": True, "pending_id": 91}
    assert db.flush_count == 1
    pending = db.added[0]
    assert pending.status == "pending"
    assert pending.request_ip == "203.0.113.10"
    assert pending.ip == "198.51.100.200"
    assert pending.devad_id == "device-ad-123"
    assert pending.dedupe_key and len(pending.dedupe_key) == 64
    stored = json.loads(pending.raw_data)
    assert "email" not in stored
    assert "phone" not in stored
    assert "ip" not in stored
    assert "user_agent" not in stored
    assert "devad_id" not in stored


async def _allow(_request_ip):
    return True


@pytest.mark.asyncio
async def test_duplicate_pending_event_is_not_inserted(monkeypatch, valid_payload):
    db = _FakeDB(existing_id=77)
    monkeypatch.setattr(
        ingest.PendingPostbackIngestService,
        "_allow_enqueue",
        staticmethod(_allow),
    )

    result = await ingest.PendingPostbackIngestService.enqueue(
        platform="partner_a",
        raw_data=valid_payload,
        request_ip="203.0.113.10",
        db=db,
    )

    assert result == {
        "queued": False,
        "reason": "duplicate",
        "pending_id": 77,
    }
    assert db.added == []
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_concurrent_duplicate_is_resolved_by_unique_key(monkeypatch, valid_payload):
    from sqlalchemy.exc import IntegrityError

    class ConcurrentDuplicateDB(_FakeDB):
        def __init__(self):
            super().__init__()
            self.query_count = 0

        async def execute(self, statement):
            if "postback_pending_queue_guard" in str(statement):
                self.guard_statement = statement
                return _ScalarResult(1)
            self.query_count += 1
            return _ScalarResult(None if self.query_count == 1 else 88)

        async def flush(self):
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    db = ConcurrentDuplicateDB()
    monkeypatch.setattr(
        ingest.PendingPostbackIngestService,
        "_allow_enqueue",
        staticmethod(_allow),
    )
    result = await ingest.PendingPostbackIngestService.enqueue(
        platform="partner_a",
        raw_data=valid_payload,
        request_ip="203.0.113.10",
        db=db,
    )

    assert result == {
        "queued": False,
        "reason": "duplicate",
        "pending_id": 88,
    }
    assert db.rollback_count == 1
    assert db.query_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_ip",
    [None, "", "unknown", "not-an-ip"],
)
async def test_invalid_source_ip_never_enters_pending_queue(
    monkeypatch, valid_payload, request_ip
):
    db = _FakeDB()
    called = False

    async def should_not_rate_limit(_ip):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(
        ingest.PendingPostbackIngestService,
        "_allow_enqueue",
        staticmethod(should_not_rate_limit),
    )
    result = await ingest.PendingPostbackIngestService.enqueue(
        platform="partner_a",
        raw_data=valid_payload,
        request_ip=request_ip,
        db=db,
    )

    assert result["queued"] is False
    assert called is False
    assert db.added == []


@pytest.mark.asyncio
async def test_invalid_fields_and_oversized_payload_are_not_stored(
    monkeypatch, valid_payload
):
    db = _FakeDB()
    monkeypatch.setattr(
        ingest.PendingPostbackIngestService,
        "_allow_enqueue",
        staticmethod(_allow),
    )

    invalid = dict(valid_payload, payout="-1")
    result = await ingest.PendingPostbackIngestService.enqueue(
        platform="partner_a",
        raw_data=invalid,
        request_ip="203.0.113.10",
        db=db,
    )
    assert result == {"queued": False, "reason": "invalid_fields"}

    oversized = dict(valid_payload, large="x" * (ingest._PENDING_RAW_DATA_MAX_BYTES + 1))
    result = await ingest.PendingPostbackIngestService.enqueue(
        platform="partner_a",
        raw_data=oversized,
        request_ip="203.0.113.10",
        db=db,
    )
    assert result == {"queued": False, "reason": "payload_too_large"}
    assert db.added == []


@pytest.mark.asyncio
async def test_full_pending_backlog_rejects_new_record(monkeypatch, valid_payload):
    db = _FakeDB(pending_count=ingest._PENDING_MAX_OPEN_RECORDS)
    monkeypatch.setattr(
        ingest.PendingPostbackIngestService,
        "_allow_enqueue",
        staticmethod(_allow),
    )

    result = await ingest.PendingPostbackIngestService.enqueue(
        platform="partner_a",
        raw_data=valid_payload,
        request_ip="203.0.113.10",
        db=db,
    )

    assert result == {"queued": False, "reason": "queue_backlog_full"}
    assert db.added == []


@pytest.mark.asyncio
async def test_rate_limiter_fails_closed_when_redis_is_unavailable(monkeypatch):
    async def no_redis():
        return None

    monkeypatch.setattr(ingest, "get_redis_client", no_redis)
    with pytest.raises(ingest.PendingPostbackQueueError):
        await ingest.PendingPostbackIngestService._allow_enqueue("203.0.113.10")


@pytest.mark.asyncio
async def test_rate_limiter_uses_atomic_redis_script_and_hashed_ip(monkeypatch):
    captured = {}

    class FakeRedis:
        async def eval(self, script, key_count, *args):
            captured.update(
                script=script,
                key_count=key_count,
                args=args,
            )
            return 1

    async def fake_redis():
        return FakeRedis()

    monkeypatch.setattr(ingest, "get_redis_client", fake_redis)
    assert await ingest.PendingPostbackIngestService._allow_enqueue(
        "203.0.113.10"
    ) is True
    assert captured["key_count"] == 4
    assert "203.0.113.10" not in " ".join(captured["args"][:2])
    assert captured["args"][2:4] == (
        "postback:pending:rate:global:hour",
        "postback:pending:rate:global:day",
    )
    assert captured["args"][4:] == (
        3600,
        86400,
        ingest._PENDING_RATE_LIMIT_PER_HOUR,
        ingest._PENDING_RATE_LIMIT_PER_DAY,
        ingest._PENDING_GLOBAL_RATE_LIMIT_PER_HOUR,
        ingest._PENDING_GLOBAL_RATE_LIMIT_PER_DAY,
    )
    assert "INCR" in captured["script"]
    assert captured["script"].index("ip_hourly > tonumber") < captured["script"].index(
        "redis.call('INCR', KEYS[3])"
    )


@pytest.mark.asyncio
async def test_rate_limiter_rejects_over_limit(monkeypatch):
    class FakeRedis:
        async def eval(self, *_args):
            return 0

    async def fake_redis():
        return FakeRedis()

    monkeypatch.setattr(ingest, "get_redis_client", fake_redis)
    assert await ingest.PendingPostbackIngestService._allow_enqueue(
        "203.0.113.10"
    ) is False


@pytest.mark.asyncio
async def test_pending_backlog_guard_uses_mysql_row_lock(monkeypatch, valid_payload):
    db = _FakeDB(pending_count=ingest._PENDING_MAX_OPEN_RECORDS - 1)
    monkeypatch.setattr(
        ingest.PendingPostbackIngestService,
        "_allow_enqueue",
        staticmethod(_allow),
    )

    result = await ingest.PendingPostbackIngestService.enqueue(
        platform="partner_a",
        raw_data=valid_payload,
        request_ip="203.0.113.10",
        db=db,
    )

    assert result == {"queued": True, "pending_id": 91}
    assert db.guard_statement is not None
    assert "FOR UPDATE" in str(db.guard_statement).upper()


@pytest.mark.asyncio
async def test_pending_backlog_guard_missing_fails_closed(monkeypatch, valid_payload):
    db = _FakeDB(guard_available=False)
    monkeypatch.setattr(
        ingest.PendingPostbackIngestService,
        "_allow_enqueue",
        staticmethod(_allow),
    )

    with pytest.raises(ingest.PendingPostbackQueueError):
        await ingest.PendingPostbackIngestService.enqueue(
            platform="partner_a",
            raw_data=valid_payload,
            request_ip="203.0.113.10",
            db=db,
        )

    assert db.added == []
    assert db.flush_count == 0
