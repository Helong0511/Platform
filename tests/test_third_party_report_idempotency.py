"""第三方广告事件日志幂等与跨事件隔离测试。"""
from __future__ import annotations

import pytest

import asyncio
from datetime import datetime

from app.core import third_party_report


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


async def test_create_report_log_persists_event_key(monkeypatch):
    class Result:
        def scalar_one_or_none(self):
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


async def test_successful_existing_event_is_not_sent_again(monkeypatch):
    async def existing_log(**kwargs):
        return 41

    async def not_claimed(report_log_id):
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
        third_party_report._claim_report_log(41),
        third_party_report._claim_report_log(41),
    )

    assert sum(result is not None for result in results) == 1
    assert all(result is None or isinstance(result, datetime) for result in results)
    assert state["commits"] == 2


async def test_report_in_progress_does_not_send_duplicate_request(monkeypatch):
    async def existing_log(**kwargs):
        return 41

    async def not_claimed(report_log_id):
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

    assert isinstance(await third_party_report._claim_report_log(41), datetime)
    sql = captured["sql"]
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

    async def claimed(report_log_id):
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
    async def renew_claimed_lease(report_log_id, lease_token, lease_seconds=300):
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
        log_id=201,
        adsid="new-adsid",
        event="Purchase",
        conversion_id="new-conversion",
    ) is True
    assert context.db.committed is True
    assert log_entry.event_key == third_party_report.build_event_idempotency_key(
        "short_link", "new-adsid", "Purchase", "new-conversion"
    )


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

    async def claim(report_log_id):
        state["claim"] += 1
        return datetime(2026, 11, 11, 12, 0, 0)

    async def attempt_state(report_log_id):
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
    async def renew_claimed_lease(report_log_id, lease_token, lease_seconds=300):
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

    async def existing_log(**kwargs):
        return 911

    async def claimed(report_log_id):
        return lease_token

    async def attempt_state(report_log_id):
        return 0, 4

    async def persist_update(report_log_id, **kwargs):
        return True

    async def expired_lease(report_log_id, token, lease_seconds=300):
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
    async def existing_log(**kwargs):
        return 910

    async def claimed(report_log_id):
        return True

    async def attempt_state(report_log_id):
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
