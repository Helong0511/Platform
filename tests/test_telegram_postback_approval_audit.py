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
