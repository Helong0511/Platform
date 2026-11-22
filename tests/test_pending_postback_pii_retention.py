"""待审批 Postback 终态 PII 生命周期回归测试。"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql

from app.services import third_party_report_pii_retention as retention


@pytest.mark.asyncio
async def test_pending_postback_retention_is_disabled_by_default_without_database(monkeypatch):
    def fail_open():
        raise AssertionError("默认关闭时不应连接数据库")

    monkeypatch.setattr(retention, "AsyncSessionLocal", fail_open)
    result = await retention.scrub_expired_pending_postback_pii()

    assert result["enabled"] is False
    assert result["retention_days"] == 0
    assert result["scrubbed"] == 0


@pytest.mark.asyncio
async def test_terminal_pending_postback_pii_is_scrubbed_but_business_identity_is_preserved(monkeypatch):
    now = datetime(2026, 11, 22, 12, 0, 0)
    approved = SimpleNamespace(
        id=11,
        status="approved",
        platform="partner_a",
        conversion_id="partner-conversion-11",
        event_name="Purchase",
        event_value=12.5,
        original_payout=10.0,
        payout=9.0,
        devad_id="device-ad-id",
        os="Android",
        carrier="carrier",
        ip="203.0.113.11",
        gid="campaign-id",
        click_id="click-token",
        click_time=now,
        raw_data='{"email":"private@example.invalid"}',
        request_ip="203.0.113.10",
        dedupe_key="a" * 64,
        telegram_message_id=123,
        telegram_chat_id="456",
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        pii_scrubbed_at=None,
    )
    pending = SimpleNamespace(
        id=12,
        status="pending",
        request_ip="203.0.113.12",
        raw_data='{"email":"must-remain@example.invalid"}',
        pii_scrubbed_at=None,
    )
    captured = {}

    class ScalarRows:
        def all(self):
            # 模拟数据库 WHERE status IN ('approved', 'rejected') 的结果。
            return [approved]

    class Result:
        def scalars(self):
            return ScalarRows()

    class FakeDB:
        async def execute(self, statement):
            compiled = statement.compile(dialect=mysql.dialect())
            captured["sql"] = str(compiled).lower()
            captured["params"] = compiled.params
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

    result = await retention.scrub_expired_pending_postback_pii(
        retention_days=90,
        batch_size=20,
    )

    assert result["enabled"] is True
    assert result["scrubbed"] == 1
    assert captured["committed"] is True
    sql = captured["sql"]
    assert "pending_postback_conversions.status in" in sql
    assert "pending_postback_conversions.pii_scrubbed_at is null" in sql
    assert "pending_postback_conversions.created_at <" in sql
    assert "for update skip locked" in sql

    assert approved.devad_id is None
    assert approved.os is None
    assert approved.carrier is None
    assert approved.ip is None
    assert approved.gid is None
    assert approved.click_id is None
    assert approved.click_time is None
    assert approved.raw_data is None
    assert approved.request_ip == ""
    assert approved.telegram_message_id is None
    assert approved.telegram_chat_id is None
    assert approved.pii_scrubbed_at == now

    # 幂等键、外部转化标识及财务/审计字段必须保留。
    assert approved.platform == "partner_a"
    assert approved.conversion_id == "partner-conversion-11"
    assert approved.event_name == "Purchase"
    assert approved.dedupe_key == "a" * 64
    assert approved.event_value == 12.5
    assert approved.original_payout == 10.0
    assert approved.payout == 9.0

    # 本服务不修改 pending；真实 SQL 过滤也必须排除 pending 状态。
    assert pending.request_ip == "203.0.113.12"
    assert pending.raw_data == '{"email":"must-remain@example.invalid"}'
    assert pending.pii_scrubbed_at is None


@pytest.mark.asyncio
async def test_pending_postback_retention_rejects_invalid_days_and_batch_size():
    with pytest.raises(ValueError):
        await retention.scrub_expired_pending_postback_pii(retention_days=-1)
    with pytest.raises(ValueError):
        await retention.scrub_expired_pending_postback_pii(
            retention_days=30,
            batch_size=1001,
        )
