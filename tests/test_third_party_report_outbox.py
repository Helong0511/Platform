"""Postback 第三方 Report Outbox 隔离单元测试。"""
from __future__ import annotations

from datetime import datetime

from app.services import third_party_report_outbox as outbox


async def _async_true():
    return True


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
    assert db.added.identity_scope == "platform_scoped"
    assert db.added.platform == "bft"
    assert db.added.destination_pixel_id is None
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
            "identity_scope": "platform_scoped",
            "platform": "bft",
            "destination_pixel_id": None,
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
        "identity_scope": "platform_scoped",
        "platform": "bft",
        "destination_pixel_id": "pixel-existing",
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


async def test_enqueue_refuses_to_auto_scope_successful_legacy_report(monkeypatch):
    import pytest
    from app.services.third_party_report_outbox import LegacyEventIdentityConflict

    existing = type(
        "Existing",
        (),
        {
            "id": 83,
            "status": "success",
            "next_retry_time": None,
            "outbox_enqueued": False,
            "identity_scope": "legacy_unresolved",
            "platform": None,
            "destination_pixel_id": None,
            "max_attempts": 3,
            "attempt_count": 1,
            "report_start_time": None,
        },
    )()

    class FakeDB:
        async def scalar(self, statement):
            return existing

        async def flush(self):
            raise AssertionError("legacy identity must not be auto-reconciled")

    with pytest.raises(LegacyEventIdentityConflict):
        await outbox.enqueue_postback_report(
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
            if "select third_party_report_logs.platform" in str(statement).lower():
                return row.platform
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

    async def claim_before_snapshot(report_id, **kwargs):
        assert report_id == 91
        assert kwargs.get("expected_scope") == "platform_scoped"
        # 模拟管理端先完成载荷修正；Worker 认领后读取到的必须是新值。
        row.email = "corrected-after-claim@example.invalid"
        return datetime(2026, 11, 11, 12, 0, 0)

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(
        outbox,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    monkeypatch.setattr(outbox, "_claim_report_log", claim_before_snapshot)
    monkeypatch.setattr(outbox, "_resolve_pixel_credentials", resolve)
    monkeypatch.setattr(outbox, "_bind_outbox_destination", lambda *args, **kwargs: _async_true())
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
    assert captured["send"]["email"] == "corrected-after-claim@example.invalid"
    assert captured["send"]["report_lease_token"] == datetime(2026, 11, 11, 12, 0, 0)


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
            if "select third_party_report_logs.platform" in str(statement).lower():
                return row.platform
            return row

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    captured = {}
    lease_token = datetime(2026, 11, 11, 12, 0, 0)

    async def resolve(**kwargs):
        return None, None, None

    async def claim(report_id, **kwargs):
        assert report_id == 92
        assert kwargs.get("expected_scope") == "platform_scoped"
        return lease_token

    async def update(report_id, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(outbox, "get_app_now_naive", lambda: datetime(2026, 11, 11, 12, 0, 0))
    monkeypatch.setattr(outbox, "_resolve_pixel_credentials", resolve)
    monkeypatch.setattr(outbox, "_bind_outbox_destination", lambda *args, **kwargs: _async_true())
    monkeypatch.setattr(outbox, "_claim_report_log", claim)
    monkeypatch.setattr(outbox, "update_report_log", update)

    result = await outbox.process_postback_report_outbox_item(92)

    assert result["retryable"] is True
    assert result["reason"] == "missing_pixel_credentials"
    assert captured["status"] == "failed"
    assert captured["next_retry_time"] == datetime(2026, 11, 11, 12, 5, 0)
    assert "access_token" not in captured
    assert captured["expected_report_start_time"] == lease_token


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
            sql = str(compiled).lower()
            if "attempt_count >=" in sql:
                captured["exhausted_sql"] = sql
                return 4
            if "identity_scope !=" in sql:
                captured["scope_blocked_sql"] = sql
                return 2
            captured["terminal_failed_sql"] = sql
            return 6

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
    assert stats == {"selected": 2, "success": 2, "retryable": 0, "failed": 0, "exhausted": 4, "terminal_failed": 6, "scope_blocked": 2}
    assert "identity_scope !=" in captured["scope_blocked_sql"]
    assert "third_party_report_logs.attempt_count >= third_party_report_logs.max_attempts" in captured["exhausted_sql"]
    assert "third_party_report_logs.pii_scrubbed_at is null" in captured["exhausted_sql"]
    assert captured["normalization_committed"] is True
    assert "update third_party_report_logs" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.status in" in captured["exhausted_update_sql"]
    update_params = " ".join(str(value).lower() for value in captured["exhausted_update_params"].values())
    assert "pending" in update_params and "failed" in update_params
    assert "third_party_report_logs.pii_scrubbed_at is null" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.report_start_time is null" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.outbox_enqueued is true" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.next_retry_time is null" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.next_retry_time <=" in captured["exhausted_update_sql"]
    assert "third_party_report_logs.next_retry_time is null" in captured["exhausted_sql"]
    assert "third_party_report_logs.status = %s" in captured["terminal_failed_sql"]
    assert "third_party_report_logs.next_retry_time is null" in captured["terminal_failed_sql"]
    assert "third_party_report_logs.pii_scrubbed_at is null" in captured["terminal_failed_sql"]
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
            if "select third_party_report_logs.platform" in str(statement).lower():
                return row.platform
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

    async def claim(report_id, **kwargs):
        assert report_id == 119
        assert kwargs.get("expected_scope") == "platform_scoped"
        return datetime(2026, 11, 11, 12, 0, 0)

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(
        outbox,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    monkeypatch.setattr(outbox, "_claim_report_log", claim)
    monkeypatch.setattr(outbox, "_resolve_pixel_credentials", resolve)
    monkeypatch.setattr(outbox, "_bind_outbox_destination", lambda *args, **kwargs: _async_true())
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


async def test_pixel_resolver_rejects_disabled_short_link_even_when_credentials_exist(monkeypatch):
    from types import SimpleNamespace

    short_link = SimpleNamespace(
        is_active=False,
        expires_at=None,
        facebook_pixel_id="pixel-disabled",
        facebook_access_token="token-disabled",
        facebook_api_version="v23.0",
    )

    class FakeDB:
        async def scalar(self, statement):
            return short_link

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(
        outbox,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )

    result = await outbox._resolve_pixel_credentials(
        short_link_id=31,
        cloak_name="disabled-cloak",
        short_code="disabled-code",
    )

    assert result == (None, None, None)


async def test_pixel_resolver_rejects_expired_short_link_even_when_credentials_exist(monkeypatch):
    from types import SimpleNamespace

    short_link = SimpleNamespace(
        is_active=True,
        expires_at=datetime(2026, 11, 10, 23, 59, 59),
        facebook_pixel_id="pixel-expired",
        facebook_access_token="token-expired",
        facebook_api_version="v23.0",
    )

    class FakeDB:
        async def scalar(self, statement):
            return short_link

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(
        outbox,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )

    result = await outbox._resolve_pixel_credentials(
        short_link_id=32,
        cloak_name="expired-cloak",
        short_code="expired-code",
    )

    assert result == (None, None, None)


async def test_pixel_resolver_marks_physically_deleted_short_link(monkeypatch):
    class FakeDB:
        async def scalar(self, statement):
            return None

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())

    try:
        await outbox._resolve_pixel_credentials(
            short_link_id=33,
            cloak_name="deleted-cloak",
            short_code="deleted-code",
        )
    except outbox.OutboxConfigReferenceDeleted:
        pass
    else:
        raise AssertionError("物理删除的短链接必须明确识别为不可恢复配置引用")


async def test_outbox_marks_deleted_short_link_terminal_without_retry(monkeypatch):
    from types import SimpleNamespace

    row = SimpleNamespace(
        id=93,
        outbox_enqueued=True,
        identity_scope="platform_scoped",
        platform="bft",
        destination_pixel_id=None,
        pii_scrubbed_at=None,
        status="pending",
        next_retry_time=datetime(2026, 11, 11, 11, 59, 0),
        adsid="fbclid-deleted",
        event="Purchase",
        conversion_id="conversion-deleted",
        email="",
        ip="",
        phone="",
        ua="",
        source="postback",
        use_hash=True,
        currency="USD",
        amount=9.0,
        click_time=None,
        event_key="stable-deleted-event",
        short_link_id=34,
        cloak_name="deleted-cloak",
        short_code="deleted-code",
    )

    class FakeDB:
        async def scalar(self, statement):
            if "select third_party_report_logs.platform" in str(statement).lower():
                return row.platform
            return row

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    captured = {}
    lease_token = datetime(2026, 11, 11, 12, 0, 0)

    async def deleted(**kwargs):
        raise outbox.OutboxConfigReferenceDeleted()

    async def claim(report_id, **kwargs):
        assert report_id == 93
        assert kwargs.get("expected_scope") == "platform_scoped"
        return lease_token

    async def update(report_id, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(outbox, "get_app_now_naive", lambda: datetime(2026, 11, 11, 12, 0, 0))
    monkeypatch.setattr(outbox, "_resolve_pixel_credentials", deleted)
    monkeypatch.setattr(outbox, "_claim_report_log", claim)
    monkeypatch.setattr(outbox, "update_report_log", update)

    result = await outbox.process_postback_report_outbox_item(93)

    assert result == {
        "success": False,
        "retryable": False,
        "reason": "short_link_deleted",
    }
    assert captured["status"] == "failed"
    assert captured["error_message"] == "短链接已删除，无法解析像素配置"
    assert captured["clear_next_retry_time"] is True
    assert captured["expected_report_start_time"] == lease_token


async def test_manual_retry_sql_rejects_deleted_short_link_events(monkeypatch):
    from sqlalchemy.dialects import mysql
    from app.core import third_party_report as report_core

    captured = {}

    class Result:
        rowcount = 0

    class FakeDB:
        async def execute(self, statement):
            compiled = statement.compile(dialect=mysql.dialect())
            captured["sql"] = str(compiled).lower()
            captured["params"] = compiled.params
            return Result()

        async def commit(self):
            return None

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(report_core, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(
        report_core,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )

    assert await report_core.retry_report_log(94) is False
    assert "third_party_report_logs.error_message is null" in captured["sql"]
    assert "third_party_report_logs.error_message !=" in captured["sql"]
    params = " ".join(str(value) for value in captured["params"].values())
    assert "短链接已删除，无法解析像素配置" in params


async def test_outbox_claims_before_reading_and_never_reads_scrubbed_payload(monkeypatch):
    """已清理事件无法认领；Worker 不应先复制载荷再检查清理状态。"""
    from types import SimpleNamespace
    from app.core import third_party_report

    row = SimpleNamespace(
        id=301,
        outbox_enqueued=True,
        identity_scope="platform_scoped",
        platform="bft",
        destination_pixel_id=None,
        pii_scrubbed_at=datetime(2026, 11, 11, 12, 0, 0),
        status="pending",
        next_retry_time=datetime(2026, 11, 11, 11, 59, 0),
    )
    captured = {"read": False}

    class FakeDB:
        async def scalar(self, statement):
            if "select third_party_report_logs.platform" in str(statement).lower():
                return row.platform
            captured["read"] = True
            return row

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    async def claim(report_log_id, **kwargs):
        assert report_log_id == 301
        assert kwargs.get("expected_scope") == "platform_scoped"
        return None

    async def status_pending(report_log_id):
        return "pending"

    async def unexpected_resolve(**kwargs):
        raise AssertionError("认领失败时不得解析配置或读取发送载荷")

    async def unexpected_send(**kwargs):
        raise AssertionError("认领失败时不得调用发送函数")

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(outbox, "_claim_report_log", claim)
    monkeypatch.setattr(outbox, "_resolve_pixel_credentials", unexpected_resolve)
    monkeypatch.setattr(outbox, "send_third_party_report", unexpected_send)
    monkeypatch.setattr(third_party_report, "_get_report_status", status_pending)

    result = await outbox.process_postback_report_outbox_item(301)

    assert result == {
        "success": False,
        "retryable": True,
        "reason": "report_in_progress",
    }
    assert captured["read"] is False


async def test_outbox_missing_config_reference_is_finalized_not_rescanned(monkeypatch):
    from datetime import datetime

    row = type(
        "ReportRow",
        (),
        {
            "id": 96,
            "outbox_enqueued": True,
            "status": "pending",
            "next_retry_time": datetime(2026, 11, 11, 11, 59, 0),
            "adsid": "fbclid-no-config",
            "event": "Purchase",
            "conversion_id": "conversion-no-config",
            "email": "",
            "ip": "",
            "phone": "",
            "ua": "",
            "source": "postback",
            "use_hash": True,
            "currency": "USD",
            "amount": 8.5,
            "click_time": None,
            "event_key": "stable-event-key-96",
            "short_link_id": None,
            "cloak_name": None,
            "short_code": None,
        },
    )()

    class FakeDB:
        async def scalar(self, statement):
            if "select third_party_report_logs.platform" in str(statement).lower():
                return row.platform
            return row

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    captured = {}
    lease_token = datetime(2026, 11, 11, 12, 0, 0)

    async def claim(report_id, **kwargs):
        assert report_id == 96
        assert kwargs.get("expected_scope") == "platform_scoped"
        return lease_token

    async def update(report_id, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(
        outbox, "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    monkeypatch.setattr(outbox, "_claim_report_log", claim)
    monkeypatch.setattr(outbox, "update_report_log", update)

    result = await outbox.process_postback_report_outbox_item(96)

    assert result["reason"] == "missing_config_reference"
    assert result["retryable"] is False
    assert captured["status"] == "failed"
    assert captured["clear_next_retry_time"] is True
    assert captured["completed_at"] == datetime(2026, 11, 11, 12, 0, 0)
    assert captured["expected_report_start_time"] == lease_token



async def test_outbox_retries_after_credentials_are_restored(monkeypatch):
    """配置暂时停用后保持可重试；配置恢复且到达重试时间后继续发送同一事件。"""
    from datetime import timedelta

    now = [datetime(2026, 11, 11, 12, 0, 0)]
    lease_token = now[0]
    row = type(
        "ReportRow",
        (),
        {
            "id": 93,
            "outbox_enqueued": True,
            "pii_scrubbed_at": None,
            "status": "pending",
            "next_retry_time": now[0] - timedelta(minutes=1),
            "attempt_count": 0,
            "max_attempts": 5,
            "adsid": "fbclid-config-recovery",
            "event": "Purchase",
            "conversion_id": "conversion-config-recovery",
            "email": "",
            "ip": "203.0.113.93",
            "phone": "",
            "ua": "recovery-test-agent",
            "source": "postback",
            "use_hash": True,
            "currency": "USD",
            "amount": 9.3,
            "click_time": None,
            "event_key": "stable-recovery-event-key",
            "short_link_id": 13,
            "cloak_name": "cloak-recovery",
            "short_code": "short-recovery",
            "report_start_time": None,
        },
    )()

    class FakeDB:
        async def scalar(self, statement):
            if "select third_party_report_logs.platform" in str(statement).lower():
                return row.platform
            return row

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    resolver_calls = 0
    update_calls = []

    async def resolve(**kwargs):
        nonlocal resolver_calls
        resolver_calls += 1
        if resolver_calls == 1:
            return None, None, None
        return "pixel-restored", "token-restored", "v23.0"

    async def claim(report_id, **kwargs):
        assert report_id == 93
        assert kwargs.get("expected_scope") == "platform_scoped"
        return lease_token

    async def update(report_id, **kwargs):
        assert report_id == 93
        update_calls.append(kwargs)
        row.status = kwargs["status"]
        row.next_retry_time = kwargs["next_retry_time"]
        row.report_start_time = kwargs["report_start_time"]
        return True

    async def send(**kwargs):
        assert kwargs["facebook_pixel_id"] == "pixel-restored"
        assert kwargs["facebook_access_token"] == "token-restored"
        assert kwargs["event_key"] == "stable-recovery-event-key"
        return {"success": True, "report_log_id": 93}

    monkeypatch.setattr(outbox, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(outbox, "get_app_now_naive", lambda: now[0])
    monkeypatch.setattr(outbox, "_resolve_pixel_credentials", resolve)
    monkeypatch.setattr(outbox, "_claim_report_log", claim)
    monkeypatch.setattr(outbox, "update_report_log", update)
    monkeypatch.setattr(outbox, "send_third_party_report", send)

    first = await outbox.process_postback_report_outbox_item(93)

    assert first["retryable"] is True
    assert first["reason"] == "missing_pixel_credentials"
    assert row.next_retry_time == datetime(2026, 11, 11, 12, 5, 0)
    assert len(update_calls) == 1

    now[0] = row.next_retry_time
    second = await outbox.process_postback_report_outbox_item(93)

    assert second == {"success": True, "report_log_id": 93}
    assert resolver_calls == 2


async def test_outbox_payload_editor_uses_row_lock_and_rejects_active_lease(monkeypatch):
    """编辑先锁定日志行，并在活动发送租约存在时拒绝修改载荷。"""
    from types import SimpleNamespace
    from sqlalchemy.dialects import mysql
    from app.core import third_party_report as report_core

    now = datetime(2026, 11, 11, 12, 0, 0)
    row = SimpleNamespace(
        id=302,
        pii_scrubbed_at=None,
        outbox_enqueued=True,
        identity_scope="platform_scoped",
        platform="bft",
        destination_pixel_id=None,
        status="failed",
        attempt_count=0,
        report_start_time=now,
        adsid="fbclid-302",
        event="Purchase",
        conversion_id="conversion-302",
        source="postback",
        email="old@example.invalid",
        ip="",
        phone="",
        ua="",
        currency="USD",
        amount=2.0,
        report_params=None,
        use_hash=True,
    )
    captured = {}

    class Scalars:
        def first(self):
            return row

    class Result:
        def scalars(self):
            return Scalars()

    class FakeDB:
        async def execute(self, statement):
            compiled = statement.compile(dialect=mysql.dialect())
            captured["sql"] = str(compiled).lower()
            return Result()

        async def commit(self):
            captured["committed"] = True

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(report_core, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(report_core, "get_app_now_naive", lambda: now)

    updated = await report_core.update_report_log_params(
        302, email="new@example.invalid"
    )

    assert updated is False
    assert "for update" in captured["sql"]
    assert "committed" not in captured
    assert row.email == "old@example.invalid"


async def test_enqueue_refuses_existing_platform_scoped_event_owned_by_another_platform():
    import pytest
    from app.services.third_party_report_outbox import LegacyEventIdentityConflict

    existing = type(
        "Existing",
        (),
        {
            "id": 84,
            "identity_scope": "platform_scoped",
            "platform": "other-platform",
            "outbox_enqueued": True,
        },
    )()

    class FakeDB:
        async def scalar(self, statement):
            return existing

        async def flush(self):
            raise AssertionError("平台不匹配时不得修改或复用事件")

    with pytest.raises(LegacyEventIdentityConflict):
        await outbox.enqueue_postback_report(
            FakeDB(),
            platform="bft",
            adsid="same-click",
            event="Purchase",
            conversion_id="same-conversion",
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
