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
