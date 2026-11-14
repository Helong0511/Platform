"""第三方广告事件日志幂等与跨事件隔离测试。"""
from __future__ import annotations

import pytest

import asyncio
from datetime import datetime

from app.core import third_party_report
from app.services import third_party_report_outbox as report_outbox


def test_event_idempotency_key_is_stable_and_event_scoped():
    view_key = third_party_report.build_event_idempotency_key(
        "postback", "ads-123", "ViewContent", None
    )
    purchase_key = third_party_report.build_event_idempotency_key(
        "postback", "ads-123", "Purchase", "conversion-456"
    )
    assert view_key == third_party_report.build_event_idempotency_key(
        "postback", "ads-123", "ViewContent", None
    )
    # Purchase 到来后补写到 ViewContent 的 conversion_id 不能改变原事件身份。
    assert view_key == third_party_report.build_event_idempotency_key(
        "postback", "ads-123", "ViewContent", "conversion-456"
    )
    assert view_key != purchase_key



@pytest.fixture(autouse=True)
def _mock_identity_lock_for_report_unit_tests(monkeypatch):
    async def no_database_lock(db, **kwargs):
        return "unit-test-identity-lock"

    monkeypatch.setattr(third_party_report, "_lock_report_base_identity", no_database_lock)
    monkeypatch.setattr(report_outbox, "_lock_report_base_identity", no_database_lock)
    async def no_legacy_conflict(db, **kwargs):
        return False

    monkeypatch.setattr(report_outbox, "_has_legacy_unresolved_base_identity", no_legacy_conflict)


async def test_create_report_log_persists_event_key(monkeypatch):
    class Result:
        def scalars(self):
            return self

        def first(self):
            return None

    class FakeDB:
        def __init__(self):
            self.added = None
            self.committed = False

        async def execute(self, statement):
            return Result()

        def add(self, value):
            self.added = value

        async def commit(self):
            self.committed = True

        async def refresh(self, value):
            value.id = 41

    class SessionContext:
        def __init__(self, db):
            self.db = db

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *args):
            return False

    fake_db = FakeDB()
    monkeypatch.setattr(
        third_party_report,
        "AsyncSessionLocal",
        lambda: SessionContext(fake_db),
    )

    log_id = await third_party_report.create_report_log(
        source="postback",
        adsid="ads-123",
        event="Purchase",
        email="",
        ip="",
        phone="",
        ua="",
        conversion_id="conversion-456",
    )

    assert log_id == 41
    assert fake_db.committed is True
    assert fake_db.added.event_key == third_party_report.build_event_idempotency_key(
        "postback", "ads-123", "Purchase", "conversion-456"
    )
    assert fake_db.added.identity_scope == "unscoped"
    assert fake_db.added.platform is None


async def test_successful_existing_event_is_not_sent_again(monkeypatch):
    async def existing_log(**kwargs):
        return 41

    async def not_claimed(report_log_id, **kwargs):
        return None

    async def existing_status(report_log_id):
        return "success"

    class UnexpectedHTTPClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("successful duplicate event must not call Facebook")

    monkeypatch.setattr(third_party_report, "create_report_log", existing_log)
    monkeypatch.setattr(third_party_report, "_claim_report_log", not_claimed)
    monkeypatch.setattr(third_party_report, "_get_report_status", existing_status)
    monkeypatch.setattr(third_party_report.httpx, "AsyncClient", UnexpectedHTTPClient)

    result = await third_party_report.send_third_party_report(
        adsid="ads-123",
        event="ViewContent",
        email=None,
        ip=None,
        phone=None,
        ua=None,
        facebook_pixel_id="isolated-pixel",
        facebook_access_token="isolated-token",
        source="postback",
    )

    assert result == {
        "success": True,
        "deduplicated": True,
        "report_log_id": 41,
    }


async def test_report_log_claim_is_atomic_for_concurrent_senders(monkeypatch):
    """两个并发发送者只有一个能取得同一事件日志的发送租约。"""
    state = {"claimed": False, "commits": 0}

    class Result:
        def __init__(self, rowcount):
            self.rowcount = rowcount

    class FakeDB:
        async def execute(self, statement):
            # 模拟数据库 UPDATE ... WHERE lease expired 的原子行数仲裁。
            if state["claimed"]:
                return Result(0)
            state["claimed"] = True
            return Result(1)

        async def commit(self):
            state["commits"] += 1

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        third_party_report,
        "AsyncSessionLocal",
        lambda: SessionContext(),
    )

    results = await asyncio.gather(
        third_party_report._claim_report_log(41, expected_scope="unscoped"),
        third_party_report._claim_report_log(41, expected_scope="unscoped"),
    )

    assert sum(result is not None for result in results) == 1
    assert all(result is None or isinstance(result, datetime) for result in results)
    assert state["commits"] == 2


async def test_report_in_progress_does_not_send_duplicate_request(monkeypatch):
    async def existing_log(**kwargs):
        return 41

    async def not_claimed(report_log_id, **kwargs):
        return None

    async def pending_status(report_log_id):
        return "pending"

    class UnexpectedHTTPClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("a concurrent sender must not call Facebook")

    monkeypatch.setattr(third_party_report, "create_report_log", existing_log)
    monkeypatch.setattr(third_party_report, "_claim_report_log", not_claimed)
    monkeypatch.setattr(third_party_report, "_get_report_status", pending_status)
    monkeypatch.setattr(third_party_report.httpx, "AsyncClient", UnexpectedHTTPClient)

    result = await third_party_report.send_third_party_report(
        adsid="ads-123",
        event="ViewContent",
        email=None,
        ip=None,
        phone=None,
        ua=None,
        facebook_pixel_id="isolated-pixel",
        facebook_access_token="isolated-token",
        source="postback",
    )

    assert result["success"] is False
    assert result["retryable"] is True
    assert result["reason"] == "report_in_progress"


async def test_report_claim_query_limits_failed_retries_to_expired_leases(monkeypatch):
    """失败状态不能绕过租约条件，否则两个并发重试仍会同时发送。"""
    from sqlalchemy.dialects import mysql

    captured = {}

    class Result:
        rowcount = 1

    class FakeDB:
        async def execute(self, statement):
            captured["sql"] = str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})).lower()
            return Result()

        async def commit(self):
            return None

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        third_party_report,
        "AsyncSessionLocal",
        lambda: SessionContext(),
    )

    assert isinstance(
        await third_party_report._claim_report_log(41, expected_scope="unscoped"),
        datetime,
    )
    sql = captured["sql"]
    assert "identity_scope = 'unscoped'" in sql
    assert "platform is null" in sql
    assert "status in" in sql
    assert "third_party_report_logs.pii_scrubbed_at is null" in sql
    assert "third_party_report_logs.attempt_count < third_party_report_logs.max_attempts" in sql
    assert "report_start_time is null" in sql
    assert "report_start_time <" in sql



async def test_manual_retry_enqueues_only_persisted_outbox_rows(monkeypatch):
    """人工重试只做持久化入队，不在请求进程创建非持久化发送任务。"""
    from datetime import datetime
    from sqlalchemy.dialects import mysql

    captured = {}

    class Result:
        rowcount = 1

    class FakeDB:
        async def execute(self, statement):
            compiled = statement.compile(dialect=mysql.dialect())
            captured["sql"] = str(compiled).lower()
            captured["params"] = {
                key: str(value).lower() for key, value in compiled.params.items()
            }
            return Result()

        async def commit(self):
            captured["committed"] = True

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        third_party_report, "AsyncSessionLocal", lambda: SessionContext()
    )
    monkeypatch.setattr(
        third_party_report, "get_app_now_naive", lambda: datetime(2026, 11, 11, 12, 0, 0)
    )

    assert await third_party_report.retry_report_log(41) is True
    assert captured["committed"] is True
    assert "third_party_report_logs.status = %s" in captured["sql"]
    assert "third_party_report_logs.outbox_enqueued is true" in captured["sql"]
    assert "third_party_report_logs.pii_scrubbed_at is null" in captured["sql"]
    assert "failed" in captured["params"].values()
    assert "next_retry_time" in captured["sql"]
    assert "report_start_time is null" in captured["sql"]
    assert "report_start_time <" in captured["sql"]


async def test_manual_retry_returns_false_when_another_request_won(monkeypatch):
    """并发管理员重试的失败方不得重复入队。"""
    class Result:
        rowcount = 0

    class FakeDB:
        async def execute(self, statement):
            return Result()

        async def commit(self):
            return None

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        third_party_report, "AsyncSessionLocal", lambda: SessionContext()
    )

    assert await third_party_report.retry_report_log(41) is False


async def test_telegram_failure_does_not_retry_successful_purchase_report(monkeypatch, caplog):
    """Meta 已确认接收 Purchase 后，通知故障不得重发，日志也不得泄露原始 PII。"""
    state = {"http_calls": 0, "statuses": [], "response_bodies": []}

    class Response:
        status_code = 200
        text = '{"events_received":1,"fbtrace_id":"trace-123"}'

        @staticmethod
        def json():
            return {"events_received": 1, "fbtrace_id": "trace-123"}

    class FakeHTTPClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            state["http_calls"] += 1
            return Response()

    async def existing_log(**kwargs):
        return 41

    async def claimed(report_log_id, **kwargs):
        return True

    async def capture_update(report_log_id, **kwargs):
        if "status" in kwargs:
            state["statuses"].append(kwargs["status"])
        if "response_body" in kwargs:
            state["response_bodies"].append(kwargs["response_body"])

    async def failed_notification(*args, **kwargs):
        raise RuntimeError("simulated Telegram outage")

    monkeypatch.setattr(third_party_report, "create_report_log", existing_log)
    monkeypatch.setattr(third_party_report, "_claim_report_log", claimed)
    async def renew_claimed_lease(report_log_id, lease_token, lease_seconds=300, **kwargs):
        return lease_token

    monkeypatch.setattr(third_party_report, "_renew_report_log_lease", renew_claimed_lease)
    monkeypatch.setattr(third_party_report, "update_report_log", capture_update)
    monkeypatch.setattr(third_party_report.httpx, "AsyncClient", FakeHTTPClient)
    monkeypatch.setattr(third_party_report, "send_telegram_message", failed_notification)
    monkeypatch.setattr(third_party_report.settings, "TELEGRAM_ADMIN", "isolated-admin")

    await third_party_report.send_third_party_report(
        adsid="ads-123",
        event="Purchase",
        email="buyer@example.invalid",
        ip="203.0.113.10",
        phone="",
        ua="test-agent",
        facebook_pixel_id="isolated-pixel",
        facebook_access_token="isolated-token",
        source="postback",
        conversion_id="conversion-456",
        currency="USD",
        amount=12.5,
    )

    assert state["http_calls"] == 1
    assert state["statuses"] == ["success"]
    assert state["response_bodies"] == [None]
    for sensitive_value in (
        "buyer@example.invalid",
        "203.0.113.10",
        "ads-123",
        "conversion-456",
        "test-agent",
    ):
        assert sensitive_value not in caplog.text



async def test_admin_identity_edit_recomputes_non_outbox_event_key(monkeypatch):
    log_entry = type(
        "ReportLog",
        (),
        {
            "id": 201,
            "source": "short_link",
            "adsid": "old-adsid",
            "event": "ViewContent",
            "conversion_id": "old-conversion",
            "event_key": "old-key",
            "outbox_enqueued": False,
            "identity_scope": "unscoped",
            "platform": None,
            "destination_pixel_id": "pixel-direct",
        },
    )()

    class Result:
        def __init__(self, row):
            self.row = row

        def scalars(self):
            return self

        def first(self):
            return self.row

    class FakeDB:
        committed = False

        async def execute(self, statement):
            sql = str(statement).lower()
            if "third_party_report_logs.event_key =" in sql:
                return Result(None)
            if "third_party_report_logs.identity_scope =" in sql:
                return Result(None)
            return Result(log_entry)

        async def commit(self):
            self.committed = True

    class SessionContext:
        def __init__(self):
            self.db = FakeDB()

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *args):
            return False

    context = SessionContext()
    monkeypatch.setattr(
        third_party_report, "AsyncSessionLocal", lambda: context
    )

    assert await third_party_report.update_report_log_params(
        log_id=201,
        adsid="new-adsid",
        event="Purchase",
        conversion_id="new-conversion",
    ) is True
    assert context.db.committed is True
    assert log_entry.event_key == third_party_report.build_event_idempotency_key(
        "short_link", "new-adsid", "Purchase", "new-conversion"
    )


async def test_admin_cannot_rewrite_attempted_direct_event_identity(monkeypatch):
    """直接发送事件一旦尝试，管理员不能改写其幂等身份与历史发送载荷。"""
    log_entry = type(
        "ReportLog",
        (),
        {
            "id": 206,
            "source": "short_link",
            "adsid": "already-sent-adsid",
            "event": "Purchase",
            "conversion_id": "already-sent-conversion",
            "event_key": "already-sent-event-key",
            "outbox_enqueued": False,
            "identity_scope": "unscoped",
            "platform": None,
            "destination_pixel_id": "pixel-direct",
            "pii_scrubbed_at": None,
            "attempt_count": 1,
            "status": "failed",
            "report_start_time": None,
            "report_success_time": None,
            "completed_at": None,
            "email": "sent@example.invalid",
        },
    )()

    class Result:
        def scalars(self):
            return self

        def first(self):
            return log_entry

    class FakeDB:
        committed = False

        async def execute(self, statement):
            return Result()

        async def commit(self):
            self.committed = True

    class SessionContext:
        def __init__(self):
            self.db = FakeDB()

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *args):
            return False

    context = SessionContext()
    monkeypatch.setattr(third_party_report, "AsyncSessionLocal", lambda: context)

    assert await third_party_report.update_report_log_params(
        log_id=206,
        adsid="rewritten-adsid",
    ) is False
    assert context.db.committed is False
    assert log_entry.adsid == "already-sent-adsid"
    assert log_entry.event_key == "already-sent-event-key"

    assert await third_party_report.update_report_log_params(
        log_id=206,
        email="rewritten@example.invalid",
    ) is False
    assert context.db.committed is False
    assert log_entry.email == "sent@example.invalid"


async def test_admin_identity_edit_rejects_unresolved_legacy_target(monkeypatch):
    """管理员编辑不能绕过创建入口对历史平台归属不明身份的拒绝策略。"""
    log_entry = type(
        "ReportLog",
        (),
        {
            "id": 205,
            "source": "short_link",
            "adsid": "old-adsid",
            "event": "Purchase",
            "conversion_id": "old-conversion",
            "event_key": "old-key",
            "outbox_enqueued": False,
            "identity_scope": "unscoped",
            "platform": None,
            "destination_pixel_id": "pixel-direct",
            "pii_scrubbed_at": None,
        },
    )()

    class Result:
        def scalars(self):
            return self

        def first(self):
            return log_entry

    class FakeDB:
        committed = False

        async def execute(self, statement):
            return Result()

        async def commit(self):
            self.committed = True

    class SessionContext:
        def __init__(self):
            self.db = FakeDB()

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *args):
            return False

    context = SessionContext()

    async def lock_identity(*args, **kwargs):
        return "locked"

    async def unresolved_target(*args, **kwargs):
        return True

    monkeypatch.setattr(third_party_report, "AsyncSessionLocal", lambda: context)
    monkeypatch.setattr(third_party_report, "_lock_report_base_identity", lock_identity)
    monkeypatch.setattr(
        third_party_report, "_has_legacy_unresolved_base_identity", unresolved_target
    )

    assert await third_party_report.update_report_log_params(
        log_id=205,
        adsid="legacy-adsid",
        event="Purchase",
        conversion_id="legacy-conversion",
    ) is False
    assert context.db.committed is False
    assert log_entry.adsid == "old-adsid"
    assert log_entry.event_key == "old-key"


async def test_admin_cannot_change_outbox_event_identity(monkeypatch):
    log_entry = type(
        "ReportLog",
        (),
        {
            "id": 202,
            "source": "postback",
            "adsid": "fbclid-original",
            "event": "Purchase",
            "conversion_id": "conversion-original",
            "event_key": "platform-scoped-event-key",
            "outbox_enqueued": True,
            "identity_scope": "platform_scoped",
            "platform": "meta",
            "destination_pixel_id": "pixel-meta",
        },
    )()

    class Result:
        def scalars(self):
            return self

        def first(self):
            return log_entry

    class FakeDB:
        committed = False

        async def execute(self, statement):
            return Result()

        async def commit(self):
            self.committed = True

    class SessionContext:
        def __init__(self):
            self.db = FakeDB()

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *args):
            return False

    context = SessionContext()
    monkeypatch.setattr(
        third_party_report, "AsyncSessionLocal", lambda: context
    )

    assert await third_party_report.update_report_log_params(
        log_id=202,
        conversion_id="conversion-mutated",
    ) is False
    assert context.db.committed is False
    assert log_entry.conversion_id == "conversion-original"
    assert log_entry.event_key == "platform-scoped-event-key"

async def test_attempted_outbox_payload_is_immutable(monkeypatch):
    from datetime import datetime

    log_entry = type(
        "ReportLog",
        (),
        {
            "id": 203,
            "source": "postback",
            "adsid": "fbclid-attempted",
            "event": "Purchase",
            "conversion_id": "conversion-attempted",
            "event_key": "stable-attempted-event-key",
            "outbox_enqueued": True,
            "identity_scope": "platform_scoped",
            "platform": "meta",
            "destination_pixel_id": "pixel-meta",
            "status": "failed",
            "attempt_count": 1,
            "report_start_time": datetime(2026, 11, 11, 11, 59, 0),
            "email": "original@example.invalid",
        },
    )()

    class Result:
        def scalars(self):
            return self

        def first(self):
            return log_entry

    class FakeDB:
        committed = False

        async def execute(self, statement):
            return Result()

        async def commit(self):
            self.committed = True

    class SessionContext:
        def __init__(self):
            self.db = FakeDB()

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *args):
            return False

    context = SessionContext()
    monkeypatch.setattr(third_party_report, "AsyncSessionLocal", lambda: context)

    assert await third_party_report.update_report_log_params(
        log_id=203,
        email="changed@example.invalid",
    ) is False
    assert context.db.committed is False
    assert log_entry.email == "original@example.invalid"


async def test_unattempted_failed_outbox_payload_can_be_corrected_after_lease_expiry(monkeypatch):
    from datetime import datetime, timedelta

    now = datetime(2026, 11, 11, 12, 0, 0)
    log_entry = type(
        "ReportLog",
        (),
        {
            "id": 204,
            "source": "postback",
            "adsid": "fbclid-not-attempted",
            "event": "Purchase",
            "conversion_id": "conversion-not-attempted",
            "event_key": "stable-not-attempted-event-key",
            "outbox_enqueued": True,
            "identity_scope": "platform_scoped",
            "platform": "meta",
            "destination_pixel_id": "pixel-meta",
            "status": "failed",
            "attempt_count": 0,
            "report_start_time": now - timedelta(seconds=third_party_report.REPORT_LOG_LEASE_SECONDS + 2),
            "email": "old@example.invalid",
        },
    )()

    class Result:
        def scalars(self):
            return self

        def first(self):
            return log_entry

    class FakeDB:
        committed = False

        async def execute(self, statement):
            return Result()

        async def commit(self):
            self.committed = True

    class SessionContext:
        def __init__(self):
            self.db = FakeDB()

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *args):
            return False

    context = SessionContext()
    monkeypatch.setattr(third_party_report, "AsyncSessionLocal", lambda: context)
    monkeypatch.setattr(third_party_report, "get_app_now_naive", lambda: now)

    assert await third_party_report.update_report_log_params(
        log_id=204,
        email="corrected@example.invalid",
    ) is True
    assert context.db.committed is True
    assert log_entry.email == "corrected@example.invalid"


async def test_remote_acceptance_with_swallowed_db_ack_failure_reuses_event_id(monkeypatch, caplog):
    """实际执行发送函数：远端接收后本地成功状态提交失败，重试仍使用相同 event_id。"""
    state = {"status": "pending", "http_event_ids": [], "ack_attempts": 0, "claim": 0}

    async def valid_existing_binding(*args, **kwargs):
        return True

    # 本测试聚焦远端 ACK 丢失后的重试语义；身份绑定由专门测试覆盖。
    monkeypatch.setattr(
        third_party_report, "_validate_existing_report_log_binding", valid_existing_binding
    )

    class Response:
        status_code = 200
        text = '{"events_received":1,"fbtrace_id":"isolated-trace"}'

        @staticmethod
        def json():
            return {"events_received": 1, "fbtrace_id": "isolated-trace"}

    class FakeHTTPClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, json, params):
            state["http_event_ids"].append(json["data"][0]["event_id"])
            return Response()

    async def claim(report_log_id, **kwargs):
        state["claim"] += 1
        assert kwargs.get("expected_scope") == "platform_scoped"
        return datetime(2026, 11, 11, 12, 0, 0)

    async def attempt_state(report_log_id, **kwargs):
        return state["ack_attempts"], 12

    async def persist_update(report_log_id, **kwargs):
        # 模拟 attempt_count 可落库，但远端成功 ACK 的本地提交失败。
        if kwargs.get("status") == "success":
            return False
        if kwargs.get("attempt_count") is not None:
            state["ack_attempts"] = kwargs["attempt_count"]
        return True

    async def read_status(report_log_id):
        return state["status"]

    monkeypatch.setattr(third_party_report, "_claim_report_log", claim)
    async def renew_claimed_lease(report_log_id, lease_token, lease_seconds=300, **kwargs):
        return lease_token

    monkeypatch.setattr(third_party_report, "_renew_report_log_lease", renew_claimed_lease)
    monkeypatch.setattr(third_party_report, "_get_report_attempt_state", attempt_state)
    monkeypatch.setattr(third_party_report, "update_report_log", persist_update)
    monkeypatch.setattr(third_party_report, "_get_report_status", read_status)
    monkeypatch.setattr(third_party_report.httpx, "AsyncClient", FakeHTTPClient)
    async def no_sleep(*_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    common = {
        "adsid": "fbclid-ack-loss",
        "event": "Purchase",
        "email": None,
        "ip": "198.51.100.77",
        "phone": None,
        "ua": None,
        "facebook_pixel_id": "isolated-pixel",
        "facebook_access_token": "isolated-token",
        "source": "postback",
        "platform": "meta",
        "conversion_id": "conversion-ack-loss",
        "currency": "USD",
        "amount": 21.0,
        "report_log_id": 119,
        "event_key": "stable-event-id-ack-loss",
    }

    first = await third_party_report.send_third_party_report(**common)
    assert first["success"] is False
    assert first["retryable"] is True
    assert first["reason"] == "report_lease_lost_after_send"
    assert state["status"] == "pending"

    # 模拟租约到期后 worker 恢复；数据库仍未确认第一次发送成功。
    second = await third_party_report.send_third_party_report(**common)
    assert second["success"] is False
    assert second["retryable"] is True
    assert state["http_event_ids"] == [
        "stable-event-id-ack-loss",
        "stable-event-id-ack-loss",
    ]
    # 原始客户端 IP 不得进入应用日志（TEST-NET 合成地址）。
    assert "198.51.100.77" not in caplog.text


@pytest.mark.asyncio
async def test_report_lease_renewal_failure_prevents_external_request(monkeypatch):
    """发送前续租失败必须 fail-closed，不能创建任何外部 HTTP 请求。"""
    lease_token = datetime(2026, 11, 12, 12, 0, 0)

    async def valid_existing_binding(*args, **kwargs):
        return True

    # 本测试单独验证租约续期失败路径。
    monkeypatch.setattr(
        third_party_report, "_validate_existing_report_log_binding", valid_existing_binding
    )

    async def existing_log(**kwargs):
        return 911

    async def claimed(report_log_id, **kwargs):
        return lease_token

    async def attempt_state(report_log_id, **kwargs):
        return 0, 4

    async def persist_update(report_log_id, **kwargs):
        return True

    async def expired_lease(report_log_id, token, lease_seconds=300, **kwargs):
        assert token == lease_token
        return None

    class UnexpectedHTTPClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("租约续期失败时不得调用第三方 HTTP API")

    monkeypatch.setattr(third_party_report, "create_report_log", existing_log)
    monkeypatch.setattr(third_party_report, "_claim_report_log", claimed)
    monkeypatch.setattr(third_party_report, "_get_report_attempt_state", attempt_state)
    monkeypatch.setattr(third_party_report, "update_report_log", persist_update)
    monkeypatch.setattr(third_party_report, "_renew_report_log_lease", expired_lease)
    monkeypatch.setattr(third_party_report.httpx, "AsyncClient", UnexpectedHTTPClient)

    result = await third_party_report.send_third_party_report(
        adsid="synthetic-lease-expired",
        event="Purchase",
        email="buyer@example.invalid",
        ip="203.0.113.21",
        phone="",
        ua="synthetic-agent",
        facebook_pixel_id="isolated-pixel",
        facebook_access_token="isolated-token",
        source="postback",
        conversion_id="synthetic-lease-expired",
        currency="USD",
        amount=18.0,
        report_log_id=911,
        event_key="stable-lease-expired-event",
    )

    assert result["success"] is False
    assert result["retryable"] is True
    assert result["reason"] == "report_lease_lost_before_send"


@pytest.mark.asyncio
async def test_report_claim_exception_does_not_leak_exception_text(monkeypatch, caplog):
    async def create_log(**kwargs):
        return 909

    async def fail_claim(report_log_id):
        raise RuntimeError("buyer@example.invalid 203.0.113.10 secret-payload")

    monkeypatch.setattr(third_party_report, "create_report_log", create_log)
    monkeypatch.setattr(third_party_report, "_claim_report_log", fail_claim)

    result = await third_party_report.send_third_party_report(
        adsid="ads-privacy-test",
        event="Purchase",
        email="buyer@example.invalid",
        ip="203.0.113.10",
        phone="",
        ua="private-agent",
        facebook_pixel_id="isolated-pixel",
        facebook_access_token="isolated-token",
        source="postback",
        conversion_id="conversion-privacy-test",
        currency="USD",
        amount=12.5,
    )

    assert result["success"] is False
    assert result["reason"] == "report_claim_unavailable"
    assert "buyer@example.invalid" not in caplog.text
    assert "203.0.113.10" not in caplog.text
    assert "secret-payload" not in caplog.text



def test_report_attempt_budget_never_exceeds_cumulative_limit():
    from app.core.third_party_report import _calculate_report_attempt_budget

    # 新事件保留原有 3 次哈希请求 + 1 次非哈希兜底语义。
    assert _calculate_report_attempt_budget(
        0, 4, use_hash=True, max_retries=3
    ) == (3, True)

    # 剩余预算为 2 时，只允许 1 次哈希 + 1 次兜底。
    assert _calculate_report_attempt_budget(
        10, 12, use_hash=True, max_retries=3
    ) == (1, True)

    # 最后 1 次预算只允许非哈希兜底，不能额外发送哈希请求。
    assert _calculate_report_attempt_budget(
        11, 12, use_hash=True, max_retries=3
    ) == (0, True)

    # 预算耗尽后不再发起任何请求。
    assert _calculate_report_attempt_budget(
        12, 12, use_hash=True, max_retries=3
    ) == (0, False)

    # 不使用哈希时，剩余预算全部用于本轮请求。
    assert _calculate_report_attempt_budget(
        10, 12, use_hash=False, max_retries=3
    ) == (2, False)


@pytest.mark.asyncio
async def test_failed_attempt_persistence_prevents_external_request(monkeypatch):
    """累计尝试次数无法持久化时，必须 fail-closed，不得调用第三方。"""
    async def valid_existing_binding(*args, **kwargs):
        return True

    # 本测试单独验证 attempt_count 持久化失败路径。
    monkeypatch.setattr(
        third_party_report, "_validate_existing_report_log_binding", valid_existing_binding
    )
    async def existing_log(**kwargs):
        return 910

    async def claimed(report_log_id, **kwargs):
        return True

    async def attempt_state(report_log_id, **kwargs):
        return 0, 4

    async def failed_persist(report_log_id, **kwargs):
        return False

    class UnexpectedHTTPClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("attempt_count 未持久化时不得调用第三方 API")

    monkeypatch.setattr(third_party_report, "create_report_log", existing_log)
    monkeypatch.setattr(third_party_report, "_claim_report_log", claimed)
    monkeypatch.setattr(third_party_report, "_get_report_attempt_state", attempt_state)
    monkeypatch.setattr(third_party_report, "update_report_log", failed_persist)
    monkeypatch.setattr(third_party_report.httpx, "AsyncClient", UnexpectedHTTPClient)

    result = await third_party_report.send_third_party_report(
        adsid="synthetic-click-id",
        event="Purchase",
        email="buyer@example.invalid",
        ip="203.0.113.19",
        phone="",
        ua="synthetic-agent",
        facebook_pixel_id="isolated-pixel",
        facebook_access_token="isolated-token",
        source="postback",
        conversion_id="synthetic-conversion",
        currency="USD",
        amount=19.0,
        report_log_id=910,
        event_key="stable-attempt-persist-test",
    )

    assert result["success"] is False
    assert result["retryable"] is True
    assert result["reason"] == "attempt_state_persist_failed"


def test_blank_platform_is_treated_as_unscoped_identity():
    """空字符串和纯空白不是有效平台标识，不应意外引入第五个空字段。"""
    legacy_key = third_party_report.build_event_idempotency_key(
        "postback", "ads-blank-platform", "Purchase", "conversion-blank"
    )
    assert third_party_report.build_event_idempotency_key(
        "postback", "ads-blank-platform", "Purchase", "conversion-blank", platform=""
    ) == legacy_key
    assert third_party_report.build_event_idempotency_key(
        "postback", "ads-blank-platform", "Purchase", "conversion-blank", platform="   "
    ) == legacy_key
    assert third_party_report.build_event_idempotency_key(
        "postback", "ads-blank-platform", "Purchase", "conversion-blank", platform=" bft "
    ) == third_party_report.build_event_idempotency_key(
        "postback", "ads-blank-platform", "Purchase", "conversion-blank", platform="bft"
    )



async def test_postback_enqueue_fails_closed_on_legacy_four_field_identity(monkeypatch):
    """历史四字段事件无法证明平台归属时，禁止新建平台作用域事件造成重复发送。"""
    from app.services.third_party_report_outbox import (
        LegacyEventIdentityConflict,
        enqueue_postback_report,
    )

    class FakeDB:
        def __init__(self):
            self.scalar_calls = 0
            self.added = []

        async def scalar(self, statement):
            self.scalar_calls += 1
            # 第一次查询当前平台五字段键不存在；第二次查询历史四字段键命中。
            return None if self.scalar_calls == 1 else 901

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            raise AssertionError("检测到历史身份冲突时不得写入新 Outbox 行")

    db = FakeDB()
    async def legacy_identity_conflict(db_arg, **kwargs):
        return True

    monkeypatch.setattr(report_outbox, "_has_legacy_unresolved_base_identity", legacy_identity_conflict)
    with pytest.raises(LegacyEventIdentityConflict):
        await enqueue_postback_report(
            db,
            platform="meta",
            adsid="legacy-click-901",
            event="Purchase",
            conversion_id="legacy-conversion-901",
            email=None,
            ip=None,
            phone=None,
            ua=None,
            currency="USD",
            amount=1.0,
            short_link_id=12,
            cloak_name=None,
            short_code=None,
            click_time=None,
        )
    assert db.scalar_calls == 0
    assert db.added == []


async def test_existing_report_log_binding_requires_persisted_identity_and_lease(monkeypatch):
    lease = datetime(2026, 11, 13, 12, 30, 0)

    class Result:
        def scalars(self):
            return self

        def first(self):
            return type(
                "ReportRow",
                (),
                {
                    "outbox_enqueued": True,
                    "identity_scope": "platform_scoped",
                    "platform": "meta",
                    "destination_pixel_id": "pixel-123",
                    "pii_scrubbed_at": None,
                    "source": "postback",
                    "adsid": "ads-123",
                    "event": "Purchase",
                    "conversion_id": "conv-456",
                    "event_key": "persisted-key",
                    "report_start_time": lease,
                },
            )()

    class FakeDB:
        async def execute(self, statement):
            return Result()

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(third_party_report, "AsyncSessionLocal", lambda: SessionContext())

    valid = await third_party_report._validate_existing_report_log_binding(
        41,
        source="postback",
        adsid="ads-123",
        event="Purchase",
        conversion_id="conv-456",
        event_key="persisted-key",
        platform="meta",
        destination_pixel_id="pixel-123",
        lease_token=lease,
    )
    wrong_payload = await third_party_report._validate_existing_report_log_binding(
        41,
        source="postback",
        adsid="other-click",
        event="Purchase",
        conversion_id="conv-456",
        event_key="persisted-key",
        platform="meta",
        destination_pixel_id="pixel-123",
        lease_token=lease,
    )
    wrong_lease = await third_party_report._validate_existing_report_log_binding(
        41,
        source="postback",
        adsid="ads-123",
        event="Purchase",
        conversion_id="conv-456",
        event_key="persisted-key",
        platform="meta",
        destination_pixel_id="pixel-123",
        lease_token=datetime(2026, 11, 13, 12, 29, 0),
    )

    assert valid is True
    assert wrong_payload is False
    assert wrong_lease is False


async def test_send_rejects_mismatched_existing_report_log_before_claim_or_http(monkeypatch):
    class Result:
        def scalars(self):
            return self

        def first(self):
            return type(
                "ReportRow",
                (),
                {
                    "outbox_enqueued": True,
                    "identity_scope": "platform_scoped",
                    "platform": "meta",
                    "destination_pixel_id": "isolated-pixel",
                    "pii_scrubbed_at": None,
                    "source": "postback",
                    "adsid": "persisted-click",
                    "event": "Purchase",
                    "conversion_id": "conv-456",
                    "event_key": "persisted-key",
                    "report_start_time": datetime(2026, 11, 13, 12, 30, 0),
                },
            )()

    class FakeDB:
        async def execute(self, statement):
            return Result()

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    async def unexpected_claim(*args, **kwargs):
        raise AssertionError("身份不匹配时不得认领租约")

    class UnexpectedHTTPClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("身份不匹配时不得调用第三方 HTTP")

    monkeypatch.setattr(third_party_report, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(third_party_report, "_claim_report_log", unexpected_claim)
    monkeypatch.setattr(third_party_report.httpx, "AsyncClient", UnexpectedHTTPClient)

    result = await third_party_report.send_third_party_report(
        adsid="attacker-controlled-click",
        event="Purchase",
        email=None,
        ip=None,
        phone=None,
        ua=None,
        facebook_pixel_id="isolated-pixel",
        facebook_access_token="isolated-token",
        source="postback",
        platform="meta",
        conversion_id="conv-456",
        report_log_id=41,
        event_key="persisted-key",
        report_lease_token=datetime(2026, 11, 13, 12, 30, 0),
    )

    assert result["success"] is False
    assert result["reason"] == "report_identity_mismatch"


async def test_purchase_viewcontent_link_requires_same_platform_and_pixel(monkeypatch):
    """平台级 Purchase 只能关联相同 platform + Pixel 的 ViewContent。"""
    from sqlalchemy.dialects import mysql

    view_content = type("ViewContentRow", (), {"conversion_id": None})()
    captured = {"committed": False, "sql": ""}

    class Result:
        def scalars(self):
            return self

        def first(self):
            return view_content

    class FakeDB:
        async def execute(self, statement):
            captured["sql"] = str(
                statement.compile(
                    dialect=mysql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            ).lower()
            return Result()

        async def commit(self):
            captured["committed"] = True

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(third_party_report, "AsyncSessionLocal", lambda: SessionContext())

    linked = await third_party_report._link_purchase_to_view_content(
        source="postback",
        adsid="shared-click",
        conversion_id="platform-a-conversion",
        report_log_id=71,
        destination_pixel_id="pixel-a",
        identity_scope="platform_scoped",
        platform="meta",
    )

    assert linked is True
    assert view_content.conversion_id == "platform-a-conversion"
    assert captured["committed"] is True
    assert "identity_scope = 'platform_scoped'" in captured["sql"]
    assert "platform = 'meta'" in captured["sql"]
    assert "destination_pixel_id = 'pixel-a'" in captured["sql"]


async def test_unscoped_purchase_viewcontent_link_requires_same_pixel(monkeypatch):
    """直接发送只能关联 unscoped 且 Pixel ID 完全相同的 ViewContent。"""
    from sqlalchemy.dialects import mysql

    view_content = type("ViewContentRow", (), {"conversion_id": None})()
    captured = {}

    class Result:
        def scalars(self):
            return self

        def first(self):
            return view_content

    class FakeDB:
        async def execute(self, statement):
            captured["sql"] = str(
                statement.compile(
                    dialect=mysql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            ).lower()
            return Result()

        async def commit(self):
            return None

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(third_party_report, "AsyncSessionLocal", lambda: SessionContext())

    linked = await third_party_report._link_purchase_to_view_content(
        source="short_link",
        adsid="direct-click",
        conversion_id="direct-conversion",
        report_log_id=72,
        destination_pixel_id="pixel-direct",
        identity_scope="unscoped",
        platform=None,
    )

    assert linked is True
    assert "identity_scope = 'unscoped'" in captured["sql"]
    assert "platform is null" in captured["sql"]
    assert "destination_pixel_id = 'pixel-direct'" in captured["sql"]


async def test_purchase_viewcontent_link_skips_when_destination_missing(monkeypatch):
    """目的地身份缺失时不得查询或修改 ViewContent。"""

    def unexpected_session():
        raise AssertionError("缺少 Pixel 目的地时不得关联 ViewContent")

    monkeypatch.setattr(third_party_report, "AsyncSessionLocal", unexpected_session)

    linked = await third_party_report._link_purchase_to_view_content(
        source="postback",
        adsid="shared-click",
        conversion_id="conversion",
        report_log_id=73,
        destination_pixel_id=None,
        identity_scope="platform_scoped",
        platform="meta",
    )

    assert linked is False


async def test_create_report_log_reuses_only_same_unscoped_pixel_destination(monkeypatch):
    class Result:
        def __init__(self, row):
            self.row = row

        def scalars(self):
            return self

        def first(self):
            return self.row

    class FakeDB:
        def __init__(self, row):
            self.row = row

        async def execute(self, statement):
            if "third_party_report_logs.identity_scope =" in str(statement).lower():
                return Result(None)
            return Result(self.row)

    class SessionContext:
        def __init__(self, row):
            self.db = FakeDB(row)

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *args):
            return False

    base = {
        "id": 88,
        "identity_scope": "unscoped",
        "platform": None,
        "destination_pixel_id": "pixel-A",
    }

    monkeypatch.setattr(
        third_party_report,
        "AsyncSessionLocal",
        lambda: SessionContext(type("ReportRow", (), base.copy())()),
    )
    same_destination = await third_party_report.create_report_log(
        source="short_link",
        adsid="same-click",
        event="Purchase",
        email="",
        ip="",
        phone="",
        ua="",
        conversion_id="same-conversion",
        destination_pixel_id="pixel-A",
    )

    monkeypatch.setattr(
        third_party_report,
        "AsyncSessionLocal",
        lambda: SessionContext(
            type("ReportRow", (), {**base, "destination_pixel_id": "pixel-B"})()
        ),
    )
    different_destination = await third_party_report.create_report_log(
        source="short_link",
        adsid="same-click",
        event="Purchase",
        email="",
        ip="",
        phone="",
        ua="",
        conversion_id="same-conversion",
        destination_pixel_id="pixel-A",
    )

    monkeypatch.setattr(
        third_party_report,
        "AsyncSessionLocal",
        lambda: SessionContext(
            type("ReportRow", (), {**base, "identity_scope": "legacy_unresolved"})()
        ),
    )
    unresolved_legacy = await third_party_report.create_report_log(
        source="short_link",
        adsid="same-click",
        event="Purchase",
        email="",
        ip="",
        phone="",
        ua="",
        conversion_id="same-conversion",
        destination_pixel_id="pixel-A",
    )

    assert same_destination == 88
    assert different_destination == 0
    assert unresolved_legacy == 0

async def test_purchase_viewcontent_link_locks_candidate_row(monkeypatch):
    """Purchase 关联必须锁定并稳定选择尚未关联的 ViewContent 行。"""
    from sqlalchemy.dialects import mysql

    captured = {}
    view_content = type("ViewContentRow", (), {"conversion_id": None})()

    class Result:
        def scalars(self):
            return self

        def first(self):
            return view_content

    class FakeDB:
        async def execute(self, statement):
            captured["sql"] = str(
                statement.compile(
                    dialect=mysql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            ).upper()
            return Result()

        async def commit(self):
            captured["committed"] = True

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        third_party_report, "AsyncSessionLocal", lambda: SessionContext()
    )

    linked = await third_party_report._link_purchase_to_view_content(
        source="postback",
        adsid="ads-123",
        conversion_id="conversion-456",
        report_log_id=99,
        destination_pixel_id="pixel-ci",
        identity_scope="unscoped",
        platform=None,
    )

    assert linked is True
    assert view_content.conversion_id == "conversion-456"
    assert captured["committed"] is True
    assert "ORDER BY THIRD_PARTY_REPORT_LOGS.ID ASC" in captured["sql"]
    assert "FOR UPDATE" in captured["sql"]
