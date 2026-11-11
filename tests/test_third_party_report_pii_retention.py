"""第三方上报 PII 生命周期清理单元测试。"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql

from app.services import third_party_report_pii_retention as retention


@pytest.mark.asyncio
async def test_retention_is_disabled_by_default_without_opening_database(monkeypatch):
    opened = False

    def fail_open():
        nonlocal opened
        opened = True
        raise AssertionError("默认关闭时不应连接数据库")

    monkeypatch.setattr(retention, "AsyncSessionLocal", fail_open)
    result = await retention.scrub_expired_third_party_report_pii(retention_days=0)

    assert result["enabled"] is False
    assert result["scrubbed"] == 0
    assert opened is False


@pytest.mark.asyncio
async def test_scrub_clears_payload_but_preserves_event_identity(monkeypatch):
    now = datetime(2026, 11, 11, 12, 0, 0)
    row = SimpleNamespace(
        id=9,
        status="success",
        event_key="stable-event-key",
        source="postback",
        adsid="fbclid-ci",
        event="Purchase",
        conversion_id="conversion-ci",
        email="alice@example.invalid",
        ip="203.0.113.9",
        phone="4155550123",
        ua="private-agent",
        report_params='{"user_data":{"em":["private"]}}',
        response_body='{"events_received":1}',
        log_id="remote-log-id",
        error_message="",
        pii_scrubbed_at=None,
    )
    captured = {}

    class ScalarRows:
        def all(self):
            return [row]

    class Result:
        def scalars(self):
            return ScalarRows()

    class FakeDB:
        async def execute(self, statement):
            compiled = statement.compile(dialect=mysql.dialect())
            sql = str(compiled).lower()
            captured.setdefault("sql", []).append(sql)
            if "postback_forward_logs" in sql:
                return type("EmptyResult", (), {"scalars": lambda self: type("Rows", (), {"all": lambda self: []})()})()
            return Result()

        async def commit(self):
            captured["committed"] = True

        async def rollback(self):
            captured["rolled_back"] = True

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(retention, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(retention, "get_app_now_naive", lambda: now)

    result = await retention.scrub_expired_third_party_report_pii(
        retention_days=180,
        batch_size=20,
    )

    assert result["enabled"] is True
    assert result["selected"] == result["scrubbed"] == 1
    assert captured["committed"] is True
    assert row.email is None
    assert row.ip is None
    assert row.phone is None
    assert row.ua is None
    assert row.report_params is None
    assert row.response_body is None
    assert row.log_id is None
    assert row.pii_scrubbed_at == now
    # 幂等与审计标识不变，避免重复事件在清理后重新入账。
    assert row.event_key == "stable-event-key"
    assert row.source == "postback"
    assert row.adsid == ""
    assert row.event == "Purchase"
    assert row.conversion_id is None
    assert row.short_link_id is None
    assert row.cloak_name is None
    assert row.short_code is None
    assert row.click_time is None
    sql = captured["sql"][0]
    assert "third_party_report_logs.pii_scrubbed_at is null" in sql
    assert "third_party_report_logs.created_at <" in sql
    assert "third_party_report_logs.status in" in sql
    assert "third_party_report_logs.attempt_count >= third_party_report_logs.max_attempts" in sql
    assert "for update skip locked" in sql


@pytest.mark.asyncio
async def test_failed_terminal_scrub_replaces_error_with_non_pii_marker(monkeypatch):
    now = datetime(2026, 11, 11, 12, 0, 0)
    row = SimpleNamespace(
        id=10,
        status="failed",
        event_key="failed-event-key",
        email="alice@example.invalid",
        ip="203.0.113.10",
        phone="4155550123",
        ua="private-agent",
        report_params='{"email":"alice@example.invalid"}',
        response_body='{"error":"alice@example.invalid"}',
        log_id="remote-log-id",
        error_message="raw response contains PII",
        pii_scrubbed_at=None,
    )

    class ScalarRows:
        def all(self):
            return [row]

    class Result:
        def scalars(self):
            return ScalarRows()

    class FakeDB:
        async def execute(self, statement):
            sql = str(statement).lower()
            if "postback_forward_logs" in sql:
                return type("EmptyResult", (), {"scalars": lambda self: type("Rows", (), {"all": lambda self: []})()})()
            return Result()

        async def commit(self):
            pass

        async def rollback(self):
            pass

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(retention, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(retention, "get_app_now_naive", lambda: now)

    await retention.scrub_expired_third_party_report_pii(retention_days=30)

    assert row.error_message == "历史上报载荷已按配置的数据保留策略清除"
    assert row.email is row.ip is row.phone is row.ua is None
    assert row.report_params is row.response_body is row.log_id is None


@pytest.mark.asyncio
async def test_invalid_retention_and_batch_size_are_rejected():
    with pytest.raises(ValueError):
        await retention.scrub_expired_third_party_report_pii(retention_days=-1)
    with pytest.raises(ValueError):
        await retention.scrub_expired_third_party_report_pii(retention_days=30, batch_size=1001)


@pytest.mark.asyncio
async def test_scrubbed_outbox_payload_is_not_editable():
    from datetime import datetime
    from types import SimpleNamespace
    from app.core.third_party_report import is_outbox_payload_editable

    row = SimpleNamespace(
        outbox_enqueued=True,
        status="failed",
        attempt_count=0,
        report_start_time=None,
        pii_scrubbed_at=datetime(2026, 11, 11, 12, 0, 0),
    )
    assert is_outbox_payload_editable(row) is False


@pytest.mark.asyncio
async def test_outbox_worker_refuses_a_scrubbed_row(monkeypatch):
    from datetime import datetime
    from app.services import third_party_report_outbox as outbox

    row = SimpleNamespace(
        id=11,
        pii_scrubbed_at=datetime(2026, 11, 11, 12, 0, 0),
        outbox_enqueued=True,
        status="pending",
        next_retry_time=datetime(2026, 11, 11, 11, 59, 0),
    )

    class FakeDB:
        async def scalar(self, statement):
            return row

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

    result = await outbox.process_postback_report_outbox_item(11)
    assert result == {
        "success": False,
        "retryable": False,
        "reason": "pii_payload_scrubbed",
    }


@pytest.mark.asyncio
async def test_completed_forward_log_payload_is_scrubbed_after_retention(monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace

    now = datetime(2026, 11, 11, 12, 0, 0)
    forward_row = SimpleNamespace(
        id=81,
        success=False,
        downstream_url="https://partner.invalid/postback?click_id=private-click",
        request_data='{"email":"alice@example.invalid"}',
        request_params='{"ip":"203.0.113.8"}',
        response_body='{"echo":"alice@example.invalid"}',
        error_message="raw partner response includes PII",
        pii_scrubbed_at=None,
    )
    captured = {"sql": []}

    class ScalarRows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return ScalarRows(self.rows)

    class FakeDB:
        async def execute(self, statement):
            sql = str(statement.compile(dialect=mysql.dialect())).lower()
            captured["sql"].append(sql)
            return Result([forward_row] if "postback_forward_logs" in sql else [])

        async def commit(self):
            captured["committed"] = True

        async def rollback(self):
            captured["rolled_back"] = True

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(retention, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(retention, "get_app_now_naive", lambda: now)

    result = await retention.scrub_expired_third_party_report_pii(retention_days=90)

    assert result["postback_forward_logs_scrubbed"] == 1
    assert captured["committed"] is True
    assert forward_row.downstream_url == "[已按保留策略清除]"
    assert forward_row.request_data is None
    assert forward_row.request_params is None
    assert forward_row.response_body is None
    assert forward_row.error_message == "历史转发载荷已按配置的数据保留策略清除"
    assert forward_row.pii_scrubbed_at == now
    sql = captured["sql"][1]
    assert "postback_forward_logs.completed_at is not null" in sql
    assert "not (exists" in sql
    assert "postback_forward_queue" in sql
    assert "for update skip locked" in sql


@pytest.mark.asyncio
async def test_forward_log_retention_clears_expanded_url_request_and_response(monkeypatch):
    now = datetime(2026, 11, 11, 12, 0, 0)
    row = SimpleNamespace(
        id=81,
        downstream_url="https://downstream.invalid/cb?email=alice%40example.invalid",
        request_data='{"email":"alice@example.invalid","ip":"203.0.113.8"}',
        request_params='{"click_id":"private-click-id"}',
        response_body='{"echo":"alice@example.invalid"}',
        error_message="response echoed alice@example.invalid",
        pii_scrubbed_at=None,
    )
    captured = {}

    class ScalarRows:
        def all(self):
            return [row]

    class Result:
        def scalars(self):
            return ScalarRows()

    class FakeDB:
        async def execute(self, statement):
            captured["sql"] = str(statement.compile(dialect=mysql.dialect())).lower()
            return Result()

        async def commit(self):
            captured["committed"] = True

        async def rollback(self):
            captured["rolled_back"] = True

    class SessionContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(retention, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(retention, "get_app_now_naive", lambda: now)

    result = await retention.scrub_expired_postback_forward_log_pii(
        retention_days=90,
        batch_size=10,
    )

    assert result["scrubbed"] == 1
    assert captured["committed"] is True
    assert row.downstream_url == "已按配置的数据保留策略清除"
    assert row.request_data is None
    assert row.request_params is None
    assert row.response_body is None
    assert row.error_message is None
    assert row.pii_scrubbed_at == now
    assert "postback_forward_logs.pii_scrubbed_at is null" in captured["sql"]
    assert "postback_forward_logs.completed_at is not null" in captured["sql"]
    assert "for update skip locked" in captured["sql"]
    assert "postback_forward_queue" in captured["sql"]
    assert "not (exists" in captured["sql"]
