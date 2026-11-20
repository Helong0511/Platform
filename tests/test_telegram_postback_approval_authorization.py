"""Telegram Postback 审批回调必须验证实际操作者用户 ID。"""
from types import SimpleNamespace
import importlib

import pytest

from app.core.config import Settings, settings
from app.core.telegram.callback_handlers.postback_approval import (
    _is_authorized_admin,
    handle_postback_approval,
)


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
