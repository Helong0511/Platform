"""Postback 审批审计必须区分 Telegram 身份并与业务状态事务一致。"""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.postback.approval_audit import add_postback_approval_audit
from app.models.postback import TelegramPostbackApprovalAudit


def test_telegram_actor_id_is_independent_and_audit_survives_pending_deletion():
    table = TelegramPostbackApprovalAudit.__table__
    assert not table.foreign_keys
    assert "actor_id" in table.c
    assert "system_user_id" not in table.c

    engine = create_engine("sqlite://")
    table.create(engine)
    with Session(engine) as db:
        event = add_postback_approval_audit(
            db,
            pending_conversion_id=77,
            conversion_id=901,
            actor_type="telegram",
            actor_id=123456789,
            source="telegram",
            action="approve",
            outcome="approved",
            previous_status="pending",
            new_status="approved",
            telegram_callback_query_id="callback-unique-77",
        )
        event.id = 1  # SQLite 的 BIGINT 主键不自动生成；MySQL 生产表由 AUTO_INCREMENT 生成。
        db.commit()

        stored = db.get(TelegramPostbackApprovalAudit, 1)
        assert stored.actor_type == "telegram"
        assert stored.actor_id == "123456789"
        assert stored.pending_conversion_id == 77
        assert stored.conversion_id == 901
        assert stored.outcome == "approved"


def test_audit_event_rolls_back_with_business_transaction():
    engine = create_engine("sqlite://")
    TelegramPostbackApprovalAudit.__table__.create(engine)
    with Session(engine) as db:
        event = add_postback_approval_audit(
            db,
            pending_conversion_id=78,
            actor_type="system_user",
            actor_id=42,
            source="web",
            action="reject",
            outcome="rejected",
            previous_status="pending",
            new_status="rejected",
        )
        event.id = 2
        db.rollback()
        count = db.scalar(select(func.count()).select_from(TelegramPostbackApprovalAudit))
        assert count == 0


def test_audit_helper_rejects_unknown_action_and_actor_type():
    class FakeDB:
        def add(self, _event):
            raise AssertionError("invalid events must be rejected before db.add")

    common = dict(
        pending_conversion_id=1,
        actor_id="123",
        source="telegram",
        action="approve",
        outcome="approved",
    )
    with pytest.raises(ValueError):
        add_postback_approval_audit(FakeDB(), **common, actor_type="system_user_typo")
    with pytest.raises(ValueError):
        add_postback_approval_audit(
            FakeDB(), **{**common, "action": "delete"}, actor_type="telegram"
        )

    # 两种新结果必须通过同一白名单校验，避免运行时写入后被 DB CHECK 拒绝。
    for outcome in ("already_processed", "duplicate_callback"):
        event = add_postback_approval_audit(
            SimpleNamespace(add=lambda value: value),
            **{**common, "outcome": outcome},
            actor_type="telegram",
        )
        assert event.outcome == outcome


def test_callback_data_parser_uses_strict_action_allowlist():
    from app.core.telegram.callback_handlers.postback_approval import (
        _parse_approval_callback_data,
    )

    assert _parse_approval_callback_data("postback_approve_12") == ("approve", 12)
    assert _parse_approval_callback_data("postback_reject_13") == ("reject", 13)
    assert _parse_approval_callback_data("postback_delete_12") is None
    assert _parse_approval_callback_data("postback_approve_0") is None
    assert _parse_approval_callback_data("postback_reject_2147483648") is None
    assert _parse_approval_callback_data("postback_approve_1_extra") is None


@pytest.mark.asyncio
async def test_unauthorized_telegram_callback_persists_denied_audit(monkeypatch):
    from app.core.telegram.callback_handlers import postback_approval as handler

    events = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def add(self, event):
            events.append(event)

        def commit(self):
            self.committed = True

    monkeypatch.setattr(handler, "_is_authorized_admin", lambda *_args: False)
    monkeypatch.setattr(handler, "get_sync_session_factory", lambda: FakeSession)

    answered = []

    class FakeQuery:
        data = "postback_approve_55"
        id = "callback-denied-55"
        from_user = SimpleNamespace(id=999999, username="guest")
        message = SimpleNamespace(
            chat_id=-100123,
            message_id=10,
            chat=SimpleNamespace(type="group"),
        )

        async def answer(self, **kwargs):
            answered.append(kwargs)

    await handler.handle_postback_approval(
        SimpleNamespace(callback_query=FakeQuery()),
        context=None,
    )

    assert answered == [{"text": "无权限执行此操作", "show_alert": True}]
    assert len(events) == 1
    event = events[0]
    assert event.actor_type == "telegram"
    assert event.actor_id == "999999"
    assert event.action == "approve"
    assert event.outcome == "denied"
    assert event.pending_conversion_id == 55
    assert event.telegram_callback_query_id == "callback-denied-55"



class _FakeTelegramSession:
    def __init__(self, pending, existing_conversion_id=None, fail_commit=False, fail_refresh=False):
        self.pending = pending
        self.results = [pending, None, existing_conversion_id]
        self.events = []
        self.fail_commit = fail_commit
        self.fail_refresh = fail_refresh
        self.committed = False
        self.rollback_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc, _tb):
        if exc_type is not None or not self.committed:
            self.rollback()
        return False

    def execute(self, _statement):
        value = self.results.pop(0)
        return SimpleNamespace(scalar_one_or_none=lambda: value)

    def add(self, event):
        if event.__class__.__name__ == "PostbackConversion":
            event.id = 9001
        self.events.append(event)

    def flush(self):
        return None

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("database transaction failed")
        self.committed = True

    def refresh(self, _event):
        if self.fail_refresh:
            raise RuntimeError("simulated post-commit refresh failure")
        return None

    def rollback(self):
        self.rollback_count += 1


def _fake_pending():
    return SimpleNamespace(
        id=77,
        status="pending",
        platform="bft",
        conversion_id="conversion-77",
        event_name="install",
        event_value=None,
        original_payout=None,
        payout=None,
        devad_id=None,
        os=None,
        carrier=None,
        ip="203.0.113.77",
        gid=None,
        product_id=None,
        client_id=None,
        click_id=None,
        click_time=None,
        raw_data=None,
        approved_at=None,
        rejected_at=None,
    )


def _patch_telegram_processor(monkeypatch, fake_session):
    from app.core.telegram.callback_handlers import postback_approval as handler
    from app.core.telegram import ptb_runtime
    from app.core.config import settings

    class FakeBot:
        def answer_callback_query(self, **_kwargs):
            return object()

        def edit_message_text(self, **_kwargs):
            return object()

    monkeypatch.setattr(settings, "TELEGRAM_TOKEN", "configured-token", raising=False)
    monkeypatch.setattr(ptb_runtime, "get_send_bot", lambda *_args, **_kwargs: FakeBot())
    monkeypatch.setattr(handler, "get_sync_session_factory", lambda: lambda: fake_session)
    monkeypatch.setattr(handler, "_api", lambda *_args, **_kwargs: None)
    return handler


def test_telegram_approval_audit_is_committed_with_conversion(monkeypatch):
    pending = _fake_pending()
    db = _FakeTelegramSession(pending)
    handler = _patch_telegram_processor(monkeypatch, db)

    handler.process_pending_conversion(
        77, "approve", "callback-approve-77", -100123, 8, 555123
    )

    audits = [event for event in db.events if event.__class__.__name__ == "TelegramPostbackApprovalAudit"]
    assert db.committed is True
    assert pending.status == "approved"
    assert len(audits) == 1
    audit = audits[0]
    assert audit.actor_type == "telegram"
    assert audit.actor_id == "555123"
    assert audit.action == "approve"
    assert audit.outcome == "approved"
    assert audit.conversion_id == 9001
    assert audit.telegram_callback_query_id == "callback-approve-77"


def test_telegram_duplicate_approval_is_audited_without_duplicate_conversion(monkeypatch):
    pending = _fake_pending()
    db = _FakeTelegramSession(pending, existing_conversion_id=321)
    handler = _patch_telegram_processor(monkeypatch, db)

    handler.process_pending_conversion(
        77, "approve", "callback-duplicate-77", -100123, 8, 555124
    )

    audits = [event for event in db.events if event.__class__.__name__ == "TelegramPostbackApprovalAudit"]
    conversions = [event for event in db.events if event.__class__.__name__ == "PostbackConversion"]
    assert db.committed is True
    assert pending.status == "approved"
    assert conversions == []
    assert len(audits) == 1
    assert audits[0].outcome == "already_exists"
    assert audits[0].conversion_id == 321


def test_telegram_rejection_is_audited_with_same_transaction(monkeypatch):
    pending = _fake_pending()
    db = _FakeTelegramSession(pending)
    handler = _patch_telegram_processor(monkeypatch, db)

    handler.process_pending_conversion(
        77, "reject", "callback-reject-77", -100123, 8, 555125
    )

    audits = [event for event in db.events if event.__class__.__name__ == "TelegramPostbackApprovalAudit"]
    assert db.committed is True
    assert pending.status == "rejected"
    assert len(audits) == 1
    assert audits[0].actor_id == "555125"
    assert audits[0].action == "reject"
    assert audits[0].outcome == "rejected"


def test_telegram_audit_is_not_committed_when_business_transaction_fails(monkeypatch):
    pending = _fake_pending()
    db = _FakeTelegramSession(pending, fail_commit=True)
    handler = _patch_telegram_processor(monkeypatch, db)

    handler.process_pending_conversion(
        77, "reject", "callback-failed-77", -100123, 8, 555126
    )

    audits = [event for event in db.events if event.__class__.__name__ == "TelegramPostbackApprovalAudit"]
    assert len(audits) == 1
    assert db.committed is False
    assert db.rollback_count >= 1


def test_telegram_already_processed_record_is_audited_without_mutation(monkeypatch):
    pending = _fake_pending()
    pending.status = "approved"
    db = _FakeTelegramSession(pending)
    handler = _patch_telegram_processor(monkeypatch, db)

    handler.process_pending_conversion(
        77, "reject", "callback-after-approved", -100123, 8, 555127
    )

    audits = [event for event in db.events if event.__class__.__name__ == "TelegramPostbackApprovalAudit"]
    assert db.committed is True
    assert pending.status == "approved"
    assert len(audits) == 1
    assert audits[0].outcome == "already_processed"
    assert audits[0].previous_status == "approved"
    assert audits[0].new_status == "approved"


def test_telegram_duplicate_callback_is_audited_separately(monkeypatch):
    pending = _fake_pending()
    db = _FakeTelegramSession(pending)
    db.results = [pending, 123]
    handler = _patch_telegram_processor(monkeypatch, db)

    handler.process_pending_conversion(
        77, "approve", "callback-replayed", -100123, 8, 555128
    )

    audits = [event for event in db.events if event.__class__.__name__ == "TelegramPostbackApprovalAudit"]
    assert db.committed is True
    assert pending.status == "pending"
    assert len(audits) == 1
    assert audits[0].outcome == "duplicate_callback"
    assert audits[0].telegram_callback_query_id is None





def test_telegram_approval_initialization_failure_uses_callback_bot(monkeypatch):
    from app.core.telegram.callback_handlers import postback_approval as handler
    from app.core.telegram import ptb_runtime

    _patch_telegram_processor(monkeypatch, _FakeTelegramSession(_fake_pending()))
    monkeypatch.setattr(
        ptb_runtime,
        "get_send_bot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bot init failed")),
    )
    delivered = []

    class FallbackBot:
        def answer_callback_query(self, **kwargs):
            delivered.append(kwargs)
            return object()

    monkeypatch.setattr(handler, "_api", lambda _chat_id, _coro: None)
    monkeypatch.setattr(
        handler.asyncio,
        "run_coroutine_threadsafe",
        lambda _coro, _loop: SimpleNamespace(result=lambda timeout: None),
    )
    handler.process_pending_conversion(
        77,
        "approve",
        "callback-init-failed",
        -100123,
        8,
        555129,
        FallbackBot(),
        SimpleNamespace(is_running=lambda: True),
    )

    assert delivered == [{
        "callback_query_id": "callback-init-failed",
        "text": "处理失败，请稍后重试",
    }]


def test_telegram_approval_session_factory_failure_returns_final_callback(monkeypatch):
    from app.core.telegram.callback_handlers import postback_approval as handler

    db = _FakeTelegramSession(_fake_pending())
    _patch_telegram_processor(monkeypatch, db)
    delivered = []

    class FakeBot:
        def answer_callback_query(self, **kwargs):
            delivered.append(kwargs)
            return object()

    monkeypatch.setattr(
        handler,
        "get_sync_session_factory",
        lambda: (_ for _ in ()).throw(RuntimeError("session factory failed")),
    )
    monkeypatch.setattr(handler, "_api", lambda _chat_id, _coro: None)

    handler.process_pending_conversion(
        77, "approve", "callback-session-init-failed", -100123, 8, 555130, FakeBot()
    )

    assert db.committed is False
    assert delivered == [{
        "callback_query_id": "callback-session-init-failed",
        "text": "处理失败，请稍后重试",
    }]


def test_post_commit_refresh_failure_does_not_report_approval_as_failed(monkeypatch):
    from app.core.telegram.callback_handlers import postback_approval as handler

    db = _FakeTelegramSession(_fake_pending(), fail_refresh=True)
    handler = _patch_telegram_processor(monkeypatch, db)
    delivered = []

    class FakeBot:
        def answer_callback_query(self, **kwargs):
            delivered.append(kwargs)
            return object()

    from app.core.telegram import ptb_runtime
    monkeypatch.setattr(ptb_runtime, "get_send_bot", lambda *_args, **_kwargs: FakeBot())
    monkeypatch.setattr(handler, "_api", lambda _chat_id, _coro: None)

    handler.process_pending_conversion(
        77, "approve", "callback-post-commit-refresh-failed", -100123, 8, 555131
    )

    assert db.committed is True
    assert delivered == [{
        "callback_query_id": "callback-post-commit-refresh-failed",
        "text": "审批已完成，但消息更新失败，请刷新记录状态",
    }]
