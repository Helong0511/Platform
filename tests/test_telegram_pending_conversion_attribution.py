"""Telegram 批准待确认 Postback 时必须保留归因并执行幂等检查。"""
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
import importlib

from app.models.models import PostbackConversion


def _pending_record(click_time):
    return SimpleNamespace(
        id=77,
        status="pending",
        platform="test-platform",
        conversion_id="conversion-77",
        event_name="install",
        event_value=None,
        original_payout=10,
        payout=9,
        devad_id=None,
        os="Android",
        carrier=None,
        ip="192.0.2.10",
        gid="202",
        product_id=5,
        client_id=6,
        click_id="trusted-click-77",
        click_time=click_time,
        raw_data="{}",
        request_ip="192.0.2.20",
        approved_at=None,
        rejected_at=None,
    )


def _install_fake_runtime(monkeypatch, execute_results):
    handler = importlib.import_module(
        "app.core.telegram.callback_handlers.postback_approval"
    )
    runtime = importlib.import_module("app.core.telegram.ptb_runtime")
    config = importlib.import_module("app.core.config")

    class FakeResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class FakeSession:
        def __init__(self):
            self.results = list(execute_results)
            self.added = []
            self.committed = False

        def execute(self, _statement):
            return FakeResult(self.results.pop(0))

        def add(self, value):
            self.added.append(value)

        def commit(self):
            self.committed = True

        def refresh(self, _value):
            return None

    fake_db = FakeSession()

    @contextmanager
    def session_scope():
        yield fake_db

    class FakeBot:
        def edit_message_text(self, **_kwargs):
            return None

        def answer_callback_query(self, **_kwargs):
            return None

    monkeypatch.setattr(handler, "get_sync_session_factory", lambda: session_scope)
    monkeypatch.setattr(handler, "_api", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "get_send_bot", lambda *_args, **_kwargs: FakeBot())
    monkeypatch.setattr(config.settings, "TELEGRAM_TOKEN", "test-token", raising=False)
    return fake_db


def test_approved_pending_postback_preserves_click_attribution(monkeypatch):
    click_time = datetime(2026, 11, 19, 10, 30, 0)
    pending = _pending_record(click_time)
    click = SimpleNamespace(
        click_time=click_time,
        offer_id=11,
        publisher_id=22,
        advertiser_id=33,
    )
    fake_db = _install_fake_runtime(monkeypatch, [pending, None, click])

    handler = importlib.import_module(
        "app.core.telegram.callback_handlers.postback_approval"
    )
    handler.process_pending_conversion(
        pending_id=77,
        action="approve",
        callback_query_id="callback-77",
        chat_id=100,
        message_id=200,
    )

    assert fake_db.committed is True
    assert pending.status == "approved"
    assert len(fake_db.added) == 1
    conversion = fake_db.added[0]
    assert isinstance(conversion, PostbackConversion)
    assert conversion.click_id == "trusted-click-77"
    assert conversion.click_time == click_time
    assert conversion.offer_id == 11
    assert conversion.publisher_id == 22
    assert conversion.advertiser_id == 33


def test_telegram_approval_does_not_duplicate_existing_conversion(monkeypatch):
    pending = _pending_record(datetime(2026, 11, 19, 10, 30, 0))
    fake_db = _install_fake_runtime(monkeypatch, [pending, 1234])

    handler = importlib.import_module(
        "app.core.telegram.callback_handlers.postback_approval"
    )
    handler.process_pending_conversion(
        pending_id=77,
        action="approve",
        callback_query_id="callback-77",
        chat_id=100,
        message_id=200,
    )

    assert fake_db.committed is True
    assert pending.status == "approved"
    assert fake_db.added == []
