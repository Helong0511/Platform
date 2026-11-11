"""Postback 第三方 Report Outbox 隔离单元测试。"""
from __future__ import annotations

from datetime import datetime

from app.services import third_party_report_outbox as outbox


async def test_enqueue_postback_report_uses_current_transaction_without_commit(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.added = None
            self.flushed = False
            self.committed = False

        async def scalar(self, statement):
            return None

        def add(self, value):
            self.added = value

        async def flush(self):
            self.flushed = True
            self.added.id = 73

        async def commit(self):
            self.committed = True

    db = FakeDB()
    monkeypatch.setattr(
        outbox,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )

    row_id = await outbox.enqueue_postback_report(
        db,
        platform="bft",
        adsid="fbclid-test",
        event="Purchase",
        conversion_id="conversion-73",
        email="buyer@example.invalid",
        ip="203.0.113.73",
        phone="",
        ua="isolated-test-agent",
        currency="USD",
        amount=12.5,
        short_link_id=9,
        cloak_name="campaign-a",
        short_code="abc123",
        click_time=datetime(2026, 11, 11, 11, 59, 0),
    )

    assert row_id == 73
    assert db.flushed is True
    assert db.committed is False
    assert db.added.outbox_enqueued is True
    assert db.added.status == "pending"
    assert db.added.short_link_id == 9
    assert db.added.cloak_name == "campaign-a"
    assert db.added.short_code == "abc123"
    assert db.added.event_key == outbox.build_event_idempotency_key(
        "postback", "fbclid-test", "Purchase", "conversion-73", platform="bft"
    )
    assert not hasattr(db.added, "facebook_access_token")


async def test_enqueue_postback_report_reuses_existing_event(monkeypatch):
    existing = type(
        "Existing",
        (),
        {
            "id": 81,
            "status": "failed",
            "next_retry_time": None,
            "outbox_enqueued": False,
            "max_attempts": 3,
        },
    )()

    class FakeDB:
        def __init__(self):
            self.flushed = False

        async def scalar(self, statement):
            return existing

        async def flush(self):
            self.flushed = True

    monkeypatch.setattr(
        outbox,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    db = FakeDB()
    row_id = await outbox.enqueue_postback_report(
        db,
        platform="bft",
        adsid="fbclid-existing",
        event="Purchase",
        conversion_id="conversion-existing",
        email=None,
        ip=None,
        phone=None,
        ua=None,
        currency="USD",
        amount=3.0,
        short_link_id=2,
        cloak_name=None,
        short_code=None,
        click_time=None,
    )

    assert row_id == 81
    assert existing.outbox_enqueued is True
    assert existing.short_link_id == 2
    assert existing.next_retry_time == datetime(2026, 11, 11, 12, 0, 0)
    assert db.flushed is True


async def test_enqueue_does_not_reopen_or_mutate_attempted_outbox_payload(monkeypatch):
    original = {
        "id": 82,
        "status": "failed",
        "next_retry_time": None,
        "outbox_enqueued": True,
        "max_attempts": 12,
        "attempt_count": 2,
        "report_start_time": None,
        "short_link_id": 20,
        "cloak_name": "original-cloak",
        "short_code": "original-code",
        "click_time": datetime(2026, 11, 11, 10, 0, 0),
        "error_message": "original failure",
    }
    existing = type("Existing", (), original.copy())()

    class FakeDB:
        async def scalar(self, statement):
            return existing

        async def flush(self):
            raise AssertionError("attempted Outbox must not be mutated or flushed")

    row_id = await outbox.enqueue_postback_report(
        FakeDB(),
        platform="bft",
        adsid="fbclid-existing-outbox",
        event="Purchase",
        conversion_id="conversion-existing-outbox",
        email="new@example.invalid",
        ip="203.0.113.82",
        phone="",
        ua="new-agent",
        currency="USD",
        amount=99.0,
        short_link_id=99,
        cloak_name="new-cloak",
        short_code="new-code",
        click_time=datetime(2026, 11, 11, 12, 0, 0),
    )

    assert row_id == 82
    for key, value in original.items():
        assert getattr(existing, key) == value


async def test_enqueue_does_not_reopen_successful_legacy_report(monkeypatch):
    existing = type(
        "Existing",
        (),
        {
            "id": 83,
            "status": "success",
            "next_retry_time": None,
            "outbox_enqueued": False,
            "max_attempts": 3,
            "attempt_count": 1,
            "report_start_time": None,
        },
    )()

    class FakeDB:
        async def scalar(self, statement):
            return existing

        async def flush(self):
            raise AssertionError("successful legacy report must not be reopened")

    row_id = await outbox.enqueue_postback_report(
        FakeDB(),
        platform="bft",
        adsid="fbclid-success-legacy",
        event="Purchase",
        conversion_id="conversion-success-legacy",
        email=None,
        ip=None,
        phone=None,
        ua=None,
        currency="USD",
        amount=1.0,
        short_link_id=5,
        cloak_name=None,
        short_code=None,
        click_time=None,
    )

    assert row_id == 83
    assert existing.outbox_enqueued is False
    assert existing.status == "success"


async def test_outbox_worker_resolves_credentials_at_send_time(monkeypatch):
    row = type(
        "ReportRow",
        (),
        {
            "id": 91,
            "outbox_enqueued": True,
            "status": "pending",
            "next_retry_time": datetime(2026, 11, 11, 11, 59, 0),
            "adsid": "fbclid-worker",
            "event": "Purchase",
            "conversion_id": "conversion-worker",
            "email": "",
            "ip": "203.0.113.91",
            "phone": "",
            "ua": "worker-test-agent",
            "source": "postback",
            "use_hash": True,
            "currency": "USD",
            "amount": 8.5,
            "click_time": None,
            "event_key": "stable-event-key",
            "short_link_id": 11,
            "cloak_name": "cloak-worker",
            "short_code": "short-worker",
        },
    )()

    class FakeDB:
        async def scalar(self, statement):
            return row

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    captured = {}
    async def resolve(**kwargs):
        captured["config_ref"] = kwargs
        return "pixel-current", "token-current", "v23.0"

    async def send(**kwargs):
        captured["send"] = kwargs
        # 兼容旧发送函数成功路径返回 None；worker 必须回读持久化状态。
        return None

    async def report_status(report_log_id):
        assert report_log_id == 91
        return "success"

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(
        outbox,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    monkeypatch.setattr(outbox, "_resolve_pixel_credentials", resolve)
    monkeypatch.setattr(outbox, "send_third_party_report", send)
    monkeypatch.setattr(
        "app.core.third_party_report._get_report_status", report_status
    )

    result = await outbox.process_postback_report_outbox_item(91)

    assert result["success"] is True
    assert captured["config_ref"] == {
        "short_link_id": 11,
        "cloak_name": "cloak-worker",
        "short_code": "short-worker",
    }
    assert captured["send"]["facebook_pixel_id"] == "pixel-current"
    assert captured["send"]["facebook_access_token"] == "token-current"
    assert captured["send"]["report_log_id"] == 91
    assert captured["send"]["event_key"] == "stable-event-key"


async def test_outbox_worker_rejects_invalid_batch_size():
    import pytest

    with pytest.raises(ValueError):
        await outbox.process_postback_report_outbox(batch_size=0)
    with pytest.raises(ValueError):
        await outbox.process_postback_report_outbox(batch_size=101)


async def test_outbox_missing_credentials_keeps_event_retryable(monkeypatch):
    from datetime import timedelta

    row = type(
        "ReportRow",
        (),
        {
            "id": 92,
            "outbox_enqueued": True,
            "status": "pending",
            "next_retry_time": datetime(2026, 11, 11, 11, 59, 0),
            "adsid": "fbclid-no-credentials",
            "event": "Purchase",
            "conversion_id": "conversion-no-credentials",
            "email": "",
            "ip": "",
            "phone": "",
            "ua": "",
            "source": "postback",
            "use_hash": True,
            "currency": "USD",
            "amount": 8.5,
            "click_time": None,
            "event_key": "stable-event-key-92",
            "short_link_id": 12,
            "cloak_name": "cloak-92",
            "short_code": "short-92",
        },
    )()

    class FakeDB:
        async def scalar(self, statement):
            return row

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    captured = {}

    async def resolve(**kwargs):
        return None, None, None

    async def claim(report_id):
        assert report_id == 92
        return True

    async def update(report_id, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(outbox, "get_app_now_naive", lambda: datetime(2026, 11, 11, 12, 0, 0))
    monkeypatch.setattr(outbox, "_resolve_pixel_credentials", resolve)
    monkeypatch.setattr(outbox, "_claim_report_log", claim)
    monkeypatch.setattr(outbox, "update_report_log", update)

    result = await outbox.process_postback_report_outbox_item(92)

    assert result["retryable"] is True
    assert result["reason"] == "missing_pixel_credentials"
    assert captured["status"] == "failed"
    assert captured["next_retry_time"] == datetime(2026, 11, 11, 12, 5, 0)
    assert "access_token" not in captured


async def test_postback_report_outbox_is_enqueued_in_conversion_session(monkeypatch):
    from app.core.postback.processor import PostbackProcessor

    class FakeResult:
        def scalars(self):
            return self

        def first(self):
            return None

    class FakeDB:
        async def execute(self, statement):
            return FakeResult()

        async def scalar(self, statement):
            return type("ShortLink", (), {"short_code": "short-ci"})()

    db = FakeDB()
    captured = {}

    async def capture_enqueue(received_db, **kwargs):
        captured["db"] = received_db
        captured["payload"] = kwargs
        return 103

    monkeypatch.setattr(
        "app.core.postback.processor.enqueue_postback_report",
        capture_enqueue,
    )

    report_id = await PostbackProcessor._enqueue_third_party_report_if_needed(
        platform="platform-ci",
        click_association={
            "click_id": "click-ci",
            "short_link_id": 55,
            "url_params": {"fbclid": "fbclid-ci"},
            "ip": "203.0.113.55",
            "user_agent": "ci-agent",
            "click_time": datetime(2026, 11, 11, 10, 0, 0),
        },
        normalized_data={"conversion_id": "conversion-ci", "payout": "12.50"},
        db=db,
    )

    assert report_id == 103
    assert captured["db"] is db
    assert captured["payload"]["platform"] == "platform-ci"
    assert captured["payload"]["event"] == "Purchase"
    assert captured["payload"]["conversion_id"] == "conversion-ci"
    assert captured["payload"]["short_link_id"] == 55
    assert captured["payload"]["short_code"] == "short-ci"


async def test_outbox_scan_is_bounded_and_filters_due_unexpired_attempts(monkeypatch):
    from sqlalchemy.dialects import mysql

    captured = {}

    class ScalarResult:
        def all(self):
            return [101, 102]

    class Result:
        def scalars(self):
            return ScalarResult()

    class FakeDB:
        async def execute(self, statement):
            compiled = statement.compile(dialect=mysql.dialect())
            sql = str(compiled).lower()
            if sql.lstrip().startswith("update "):
                captured["exhausted_update_sql"] = sql
                captured["exhausted_update_params"] = compiled.params
            else:
                captured["sql"] = sql
                captured["params"] = {
                    key: str(value).lower() for key, value in compiled.params.items()
                }
            return Result()

        async def commit(self):
            captured["normalization_committed"] = True

        async def scalar(self, statement):
            compiled = statement.compile(dialect=mysql.dialect())
            captured["exhausted_sql"] = str(compiled).lower()
            return 4

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    processed = []

    async def process_item(report_id):
        processed.append(report_id)
        return {"success": True}

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(
        outbox,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    monkeypatch.setattr(outbox, "process_postback_report_outbox_item", process_item)

    stats = await outbox.process_postback_report_outbox(batch_size=2)

    assert processed == [101, 102]
    assert stats == {"selected": 2, "success": 2, "retryable": 0, "failed": 0, "exhausted": 4}
    assert "third_party_report_logs.attempt_count >= third_party_report_logs.max_attempts" in captured["exhausted_sql"]
    assert captured["normalization_committed"] is True
    assert "update third_party_report_logs" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.status in" in captured["exhausted_update_sql"]
    update_params = " ".join(str(value).lower() for value in captured["exhausted_update_params"].values())
    assert "pending" in update_params and "failed" in update_params
    assert "third_party_report_logs.pii_scrubbed_at is null" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.report_start_time is null" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.outbox_enqueued is true" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.outbox_enqueued is true" in captured["sql"]
    assert "third_party_report_logs.next_retry_time <= %s" in captured["sql"]
    assert "third_party_report_logs.attempt_count < third_party_report_logs.max_attempts" in captured["sql"]
    assert "third_party_report_logs.report_start_time is null" in captured["sql"]
    assert "limit %s" in captured["sql"]

async def test_remote_acceptance_with_lost_local_ack_retries_same_event_id(monkeypatch):
    """模拟远端已接收、但本地 success ACK 未落库；恢复后必须复用稳定 event_id。"""
    row = type(
        "ReportRow",
        (),
        {
            "id": 119,
            "outbox_enqueued": True,
            "status": "pending",
            "next_retry_time": datetime(2026, 11, 11, 11, 59, 0),
            "adsid": "fbclid-ack-lost",
            "event": "Purchase",
            "conversion_id": "conversion-ack-lost",
            "email": "",
            "ip": "",
            "phone": "",
            "ua": "",
            "source": "postback",
            "use_hash": True,
            "currency": "USD",
            "amount": 19.0,
            "click_time": None,
            "event_key": "stable-event-id-ack-lost",
            "short_link_id": 19,
            "cloak_name": None,
            "short_code": None,
        },
    )()

    class FakeDB:
        async def scalar(self, statement):
            return row

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    remote_accepted = set()
    attempts = []
    status_reads = 0

    async def resolve(**kwargs):
        return "pixel-ci", "token-ci", "v23.0"

    async def send(**kwargs):
        # 代表 HTTP 200/events_received；第一次模拟本地 ACK COMMIT 丢失，
        # 发送函数无法确认本地状态，第二次由相同 event_id 幂等去重。
        event_id = kwargs["event_key"]
        attempts.append(event_id)
        remote_accepted.add(event_id)
        return None

    async def report_status(report_log_id):
        nonlocal status_reads
        assert report_log_id == 119
        status_reads += 1
        return "pending" if status_reads == 1 else "success"

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(
        outbox,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    monkeypatch.setattr(outbox, "_resolve_pixel_credentials", resolve)
    monkeypatch.setattr(outbox, "send_third_party_report", send)
    monkeypatch.setattr(
        "app.core.third_party_report._get_report_status", report_status
    )

    first = await outbox.process_postback_report_outbox_item(119)
    second = await outbox.process_postback_report_outbox_item(119)

    assert first == {
        "success": False,
        "retryable": True,
        "reason": "report_status_not_confirmed",
        "report_log_id": 119,
    }
    assert second["success"] is True
    assert attempts == ["stable-event-id-ack-lost", "stable-event-id-ack-lost"]
    assert remote_accepted == {"stable-event-id-ack-lost"}
