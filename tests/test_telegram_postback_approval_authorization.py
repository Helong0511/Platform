"""Telegram Postback 审批回调必须验证实际操作者用户 ID，并避免向聊天泄露来源 IP。"""
from types import SimpleNamespace
import importlib

import pytest

from app.core.config import Settings, settings
from app.core.telegram.callback_handlers.postback_approval import (
    _build_rejection_message,
    _is_authorized_admin,
)


def test_rejection_message_does_not_disclose_request_ip():
    message = _build_rejection_message(
        conversion_id="conversion-123",
        platform="bft",
    )

    assert "conversion-123" in message
    assert "bft" in message
    assert "IP:" not in message
    assert "request_ip" not in message


def test_private_admin_chat_id_is_backward_compatible(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN_USER_IDS", None, raising=False)
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN", "123456789", raising=False)

    assert _is_authorized_admin(123456789, "private") is True
    assert _is_authorized_admin(123456789, "group") is False
    assert _is_authorized_admin(987654321, "private") is False


def test_group_approval_requires_explicit_user_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN", "-100123456789", raising=False)
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN_USER_IDS", None, raising=False)

    assert _is_authorized_admin(123456789, "group") is False


def test_explicit_user_allowlist_authorizes_group_operator(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN", "-100123456789", raising=False)
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN_USER_IDS", "123456789,987654321", raising=False)

    assert _is_authorized_admin(123456789, "group") is True
    assert _is_authorized_admin(987654321, "group") is True
    assert _is_authorized_admin(555555555, "group") is False


def test_admin_user_id_configuration_rejects_invalid_values():
    assert Settings.validate_telegram_admin_user_ids("123, 456") == "123,456"
    with pytest.raises(ValueError):
        Settings.validate_telegram_admin_user_ids("123,-456")


@pytest.mark.asyncio
async def test_unauthorized_group_callback_is_rejected_without_starting_approval(monkeypatch):
    handler = importlib.import_module(
        "app.core.telegram.callback_handlers.postback_approval"
    )
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN_USER_IDS", None, raising=False)
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN", "-100123456789", raising=False)

    answered = []
    logs = []
    monkeypatch.setattr(handler.logger, "warning", lambda *args: logs.append(args))

    class FakeQuery:
        data = "postback_approve_77"
        id = "callback-77"
        from_user = SimpleNamespace(id=555555555, username="not-admin", first_name="Guest")
        message = SimpleNamespace(
            chat_id=-100123456789,
            message_id=42,
            chat=SimpleNamespace(type="group"),
        )

        async def answer(self, **kwargs):
            answered.append(kwargs)

    await handler.handle_postback_approval(
        SimpleNamespace(callback_query=FakeQuery()),
        context=None,
    )

    assert answered == [{"text": "无权限执行此操作", "show_alert": True}]
    rendered_logs = repr(logs)
    assert "55***5555" in rendered_logs
    assert "555555555" not in rendered_logs


@pytest.mark.asyncio
async def test_authorized_approval_callback_logs_masked_user_id(monkeypatch):
    handler = importlib.import_module(
        "app.core.telegram.callback_handlers.postback_approval"
    )
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN_USER_IDS", "123456789", raising=False)
    logs = []
    monkeypatch.setattr(handler.logger, "info", lambda *args: logs.append(args))

    from app.core.telegram import approval_worker

    submitted = []
    monkeypatch.setattr(
        approval_worker,
        "submit_approval_task",
        lambda *args: submitted.append(args) or "submitted",
    )

    class FakeQuery:
        data = "postback_approve_77"
        id = "callback-77"
        from_user = SimpleNamespace(id=123456789, username="admin", first_name="Admin")
        message = SimpleNamespace(
            chat_id=123456789,
            message_id=42,
            chat=SimpleNamespace(type="private"),
        )

        async def answer(self, **_kwargs):
            return None

    await handler.handle_postback_approval(
        SimpleNamespace(callback_query=FakeQuery()),
        context=None,
    )

    rendered_logs = repr(logs)
    assert "12***6789" in rendered_logs
    assert "123456789" not in rendered_logs
    assert len(submitted) == 1
    assert submitted[0][0] == 77
