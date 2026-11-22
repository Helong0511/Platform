"""Telegram Chat ID 日志脱敏与管理 API 异步发送回归测试。"""
import asyncio
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
    monkeypatch.setattr(telegram_api.telegram_bot_state, "bot_initialized", True)
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
    monkeypatch.setattr(telegram_api.telegram_bot_state, "bot_initialized", True)
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


@pytest.mark.asyncio
async def test_run_on_send_loop_async_offloads_blocking_wait(monkeypatch):
    from app.core.telegram import ptb_runtime

    calls = []
    monkeypatch.setattr(
        ptb_runtime,
        "run_on_send_loop",
        lambda coro, *, timeout=None: calls.append((coro, timeout)) or "done",
    )

    marker = object()
    result = await ptb_runtime.run_on_send_loop_async(marker, timeout=7.0)

    assert result == "done"
    assert calls == [(marker, 7.0)]


@pytest.mark.asyncio
async def test_telegram_diagnostic_awaits_send_loop_calls(monkeypatch):
    from app.api_v1.external import telegram as telegram_api
    from app.core.telegram import ptb_runtime

    monkeypatch.setattr(telegram_api.telegram_bot_state, "bot_initialized", True)
    monkeypatch.setattr(telegram_api.telegram_bot_state, "TELEBOT_AVAILABLE", True)
    monkeypatch.setattr(telegram_api.telegram_bot_state, "application", None)
    monkeypatch.setattr(telegram_api.settings, "TELEGRAM_TOKEN", "configured-token", raising=False)
    monkeypatch.setattr(
        telegram_api.threading,
        "enumerate",
        lambda: [SimpleNamespace(name="TelegramBot", is_alive=lambda: True)],
    )
    fake_bot = SimpleNamespace(get_webhook_info=lambda: object(), get_me=lambda: object())
    monkeypatch.setattr(ptb_runtime, "get_send_bot", lambda _token: fake_bot)
    monkeypatch.setattr(ptb_runtime, "count_application_handlers", lambda _app: 2)
    run_async = AsyncMock(side_effect=[SimpleNamespace(url=""), SimpleNamespace(username="testbot", id=123)])
    monkeypatch.setattr(ptb_runtime, "run_on_send_loop_async", run_async)

    await telegram_api.diagnostic_bot(SimpleNamespace())

    assert run_async.await_count == 2


@pytest.mark.asyncio
async def test_reset_webhook_awaits_send_loop_calls(monkeypatch):
    from app.api_v1.external import telegram as telegram_api
    from app.core.telegram import ptb_runtime

    monkeypatch.setattr(telegram_api.telegram_bot_state, "bot_initialized", True)
    monkeypatch.setattr(telegram_api.telegram_bot_state, "TELEBOT_AVAILABLE", True)
    monkeypatch.setattr(telegram_api.settings, "TELEGRAM_TOKEN", "configured-token", raising=False)
    fake_bot = SimpleNamespace(
        delete_webhook=lambda **_kwargs: asyncio.sleep(0),
        get_webhook_info=lambda: asyncio.sleep(0),
    )
    monkeypatch.setattr(ptb_runtime, "get_send_bot", lambda _token: fake_bot)
    calls = []

    async def fake_run(coro, *, timeout=None):
        calls.append(timeout)
        coro.close()
        return None if timeout == 20.0 else SimpleNamespace(url="")

    monkeypatch.setattr(ptb_runtime, "run_on_send_loop_async", fake_run)
    monkeypatch.setattr(telegram_api, "log_user_action", AsyncMock())
    monkeypatch.setattr(telegram_api, "commit_audit_log", AsyncMock())

    await telegram_api.reset_webhook(SimpleNamespace(), object(), SimpleNamespace(username="admin"))

    assert calls == [20.0, 15.0]


@pytest.mark.asyncio
async def test_start_command_uses_throttled_sender_and_escapes_user_name(monkeypatch):
    from app.core.telegram.command_handlers import start_command
    from app.core.telegram.command_handlers import stats_command

    send_async = AsyncMock(return_value=True)
    monkeypatch.setattr(start_command, "send_telegram_message_async", send_async)
    monkeypatch.setattr(stats_command, "send_stats_menu", lambda _chat_id: True)

    update = SimpleNamespace(
        effective_message=SimpleNamespace(chat_id=123456789),
        effective_user=SimpleNamespace(first_name="<b>unsafe</b>"),
    )
    await start_command.cmd_start(update, SimpleNamespace())

    send_async.assert_awaited_once()
    sent_text = send_async.await_args.args[1]
    assert "&lt;b&gt;unsafe&lt;/b&gt;" in sent_text
    assert "<b>unsafe</b>" not in sent_text


@pytest.mark.asyncio
async def test_help_command_uses_throttled_sender(monkeypatch):
    from app.core.telegram.command_handlers import help_command

    send_async = AsyncMock(return_value=True)
    monkeypatch.setattr(help_command, "send_telegram_message_async", send_async)
    update = SimpleNamespace(effective_message=SimpleNamespace(chat_id=123456789))

    await help_command.cmd_help(update, SimpleNamespace())

    send_async.assert_awaited_once()
    assert send_async.await_args.kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_id_command_uses_throttled_sender_and_escapes_group_title(monkeypatch):
    from app.core.telegram.command_handlers import id_command

    send_async = AsyncMock(return_value=True)
    monkeypatch.setattr(id_command, "send_telegram_message_async", send_async)
    chat = SimpleNamespace(id=-1001234567890, type="supergroup", title="<b>unsafe group</b>")
    message = SimpleNamespace(
        chat=chat,
        chat_id=chat.id,
        message_id=7,
        text="/id",
        entities=[],
    )
    user = SimpleNamespace(username="admin", first_name="Admin", id=123456789)
    context = SimpleNamespace(bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="testbot"))))

    await id_command.get_chat_id(SimpleNamespace(effective_message=message, effective_user=user), context)

    send_async.assert_awaited_once()
    sent_text = send_async.await_args.args[1]
    assert "&lt;b&gt;unsafe group&lt;/b&gt;" in sent_text
    assert "<b>unsafe group</b>" not in sent_text
    assert send_async.await_args.kwargs["reply_to_message_id"] == 7


@pytest.mark.asyncio
async def test_async_admin_notification_uses_async_sender(monkeypatch):
    from app.core.telegram import message_sender

    monkeypatch.setattr(message_sender, "is_telegram_enabled", lambda: True)
    send_async = AsyncMock(return_value=True)
    monkeypatch.setattr(message_sender, "send_telegram_message_async", send_async)

    result = await message_sender.send_admin_notification(
        "后台通知",
        "123456789",
        notification_type="system",
    )

    assert result is True
    send_async.assert_awaited_once_with("123456789", "⚠️ 后台通知")
