"""Telegram Chat ID 日志脱敏与管理 API 异步发送回归测试。"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.telegram_utils import mask_telegram_chat_id


def test_mask_telegram_chat_id_handles_private_group_multiple_and_invalid_values():
    assert mask_telegram_chat_id("123456789") == "12***6789"
    assert mask_telegram_chat_id("-1001234567890") == "-100****7890"
    assert mask_telegram_chat_id("1234") == "****"
    assert mask_telegram_chat_id("123456789, -1001234567890") == "12***6789,-100****7890"
    assert mask_telegram_chat_id("not-a-chat-id") == "[已隐藏]"
    assert mask_telegram_chat_id(None) == "[未提供]"


def test_redis_rate_limit_keys_do_not_contain_raw_chat_ids(monkeypatch):
    from app.core.telegram import message_sender
    from app.core.config import settings

    monkeypatch.setattr(settings, "SECRET_KEY", "unit-test-hmac-secret", raising=False)
    chat_id = "-1001234567890"
    identifier = message_sender._redis_chat_identifier(chat_id)

    assert len(identifier) == 64
    assert chat_id not in identifier
    assert identifier == message_sender._redis_chat_identifier(chat_id)
    assert identifier != message_sender._redis_chat_identifier("-1001234567891")


def test_sync_sender_logs_masked_chat_id(monkeypatch):
    from app.core.telegram import message_sender

    class FakeBot:
        def send_message(self, **_kwargs):
            return object()

    monkeypatch.setattr(message_sender, "is_telegram_enabled", lambda: True)
    monkeypatch.setattr(message_sender, "_check_bot_available", lambda: (True, "Bot 可用"))
    monkeypatch.setattr(message_sender, "_get_send_bot", lambda: FakeBot())
    monkeypatch.setattr(message_sender, "_acquire_send_mutex", lambda: "")
    monkeypatch.setattr(message_sender, "_release_send_mutex", lambda _token: None)
    monkeypatch.setattr(message_sender, "_wait_before_send", lambda _chat_id: None)
    monkeypatch.setattr(message_sender, "_sync_bot_call", lambda _coro: object())
    monkeypatch.setattr(message_sender, "MAX_RETRIES", 1)

    logs = []
    monkeypatch.setattr(
        message_sender.logger,
        "info",
        lambda message, *args, **_kwargs: logs.append(message % args if args else message),
    )

    success, reason = message_sender.send_telegram_message_result(
        "-1001234567890",
        "测试消息",
    )

    rendered = repr(logs) + reason
    assert success is True
    assert "-100****7890" in rendered
    assert "-1001234567890" not in rendered


@pytest.mark.asyncio
async def test_admin_send_endpoint_awaits_async_sender_and_masks_audit_chat_id(monkeypatch):
    from app.api_v1.external import telegram as telegram_api

    monkeypatch.setattr(telegram_api.settings, "TELEGRAM_ENABLE", True)
    monkeypatch.setattr(telegram_api, "bot_initialized", True)
    send_async = AsyncMock(return_value=True)
    monkeypatch.setattr(telegram_api, "send_telegram_message_async", send_async)
    audit = AsyncMock()
    monkeypatch.setattr(telegram_api, "log_user_action", audit)
    monkeypatch.setattr(telegram_api, "commit_audit_log", AsyncMock())

    chat_id = "-1001234567890"
    await telegram_api.send_message(
        SimpleNamespace(),
        telegram_api.SendMessageRequest(message="测试消息", chat_id=chat_id),
        SimpleNamespace(username="admin"),
        object(),
    )

    send_async.assert_awaited_once_with(chat_id, "测试消息")
    details = audit.await_args.kwargs["details"]
    assert details == {"chat_id_masked": "-100****7890"}
    assert chat_id not in repr(details)


@pytest.mark.asyncio
async def test_admin_test_endpoint_awaits_async_sender(monkeypatch):
    from app.api_v1.external import telegram as telegram_api

    monkeypatch.setattr(telegram_api.settings, "TELEGRAM_ENABLE", True)
    monkeypatch.setattr(telegram_api.settings, "TIMEZONE", "UTC", raising=False)
    monkeypatch.setattr(telegram_api, "bot_initialized", True)
    monkeypatch.setattr(
        telegram_api,
        "get_app_now",
        lambda: datetime(2026, 11, 22, 12, 0, 0),
    )
    send_async = AsyncMock(return_value=True)
    monkeypatch.setattr(telegram_api, "send_telegram_message_async", send_async)
    monkeypatch.setattr(telegram_api, "log_user_action", AsyncMock())
    monkeypatch.setattr(telegram_api, "commit_audit_log", AsyncMock())

    await telegram_api.test_bot_connection(
        SimpleNamespace(),
        object(),
        SimpleNamespace(username="admin"),
    )

    send_async.assert_awaited_once()
