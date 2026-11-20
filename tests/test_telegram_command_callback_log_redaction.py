"""Telegram 命令与回调异常日志不得包含 API 异常正文。"""
import asyncio
from types import SimpleNamespace

from app.core.telegram.command_handlers import id_command, stats_command
from app.core.telegram.callback_handlers import menu_callbacks, stats_callbacks
from app.core.telegram import stats_service


class _SecretTelegramError(RuntimeError):
    pass


def _assert_safe_logs(logs):
    rendered = repr(logs)
    assert "_SecretTelegramError" in rendered
    assert "botTOPSECRET" not in rendered
    assert "private-password" not in rendered
    assert "api.telegram.org" not in rendered


def test_id_command_redacts_get_me_error(monkeypatch):
    logs = []
    monkeypatch.setattr(id_command.logger, "warning", lambda *args, **_kwargs: logs.append(args))

    class Bot:
        async def get_me(self):
            raise _SecretTelegramError("token=private-password https://api.telegram.org/botTOPSECRET")

        async def send_message(self, **_kwargs):
            return None

    update = SimpleNamespace(
        effective_message=SimpleNamespace(
            chat=SimpleNamespace(type="supergroup", id=-100123, title="test group"),
            text="/id", entities=None, message_id=7,
        ),
        effective_user=SimpleNamespace(username="tester", first_name="Tester", id=456),
    )
    asyncio.run(id_command.get_chat_id(update, SimpleNamespace(bot=Bot())))
    _assert_safe_logs(logs)


def test_stats_menu_command_redacts_api_error(monkeypatch):
    from app.core.telegram import ptb_runtime, message_sender
    from app.core.config import settings

    logs = []
    monkeypatch.setattr(stats_command.logger, "error", lambda *args, **_kwargs: logs.append(args))
    monkeypatch.setattr(ptb_runtime, "PTB_AVAILABLE", True)
    monkeypatch.setattr(ptb_runtime, "get_send_bot", lambda *_args, **_kwargs: SimpleNamespace(edit_message_text=lambda **_kwargs: object()))
    monkeypatch.setattr(ptb_runtime, "build_inline_keyboard", lambda _buttons: object())
    monkeypatch.setattr(message_sender, "call_telegram_api_throttled", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        _SecretTelegramError("private-password https://api.telegram.org/botTOPSECRET")
    ))
    monkeypatch.setattr(settings, "TELEGRAM_TOKEN", "configured-token", raising=False)

    assert stats_command.send_stats_menu(123, message_id=7) is False
    _assert_safe_logs(logs)


def test_menu_callback_answer_error_is_redacted(monkeypatch):
    logs = []
    monkeypatch.setattr(menu_callbacks.logger, "warning", lambda *args, **_kwargs: logs.append(args))

    class Query:
        data = "View"
        message = object()

        async def answer(self):
            raise _SecretTelegramError("private-password https://api.telegram.org/botTOPSECRET")

        async def edit_message_text(self, **_kwargs):
            return None

    asyncio.run(menu_callbacks.handle_menu_callbacks(SimpleNamespace(callback_query=Query()), None))
    _assert_safe_logs(logs)


def test_stats_callback_answer_error_is_redacted(monkeypatch):
    logs = []
    monkeypatch.setattr(stats_callbacks.logger, "warning", lambda *args, **_kwargs: logs.append(args))

    class Thread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            return None

    monkeypatch.setattr(stats_callbacks.threading, "Thread", Thread)

    class Query:
        data = "stats_yesterday"
        message = SimpleNamespace(chat_id=123, message_id=7)

        async def answer(self, **_kwargs):
            raise _SecretTelegramError("private-password https://api.telegram.org/botTOPSECRET")

    asyncio.run(stats_callbacks.handle_stats_callbacks(SimpleNamespace(callback_query=Query()), None))
    _assert_safe_logs(logs)


def test_stats_service_redacts_database_error(monkeypatch):
    logs = []
    monkeypatch.setattr(stats_service.logger, "error", lambda *args, **_kwargs: logs.append(args))
    def fail_run(coro, **_kwargs):
        coro.close()
        raise _SecretTelegramError("private-password mysql://root:secret@db/private")

    monkeypatch.setattr(stats_service.asyncio, "run", fail_run)

    assert stats_service.fetch_stats_sync("stats_yesterday") is None
    _assert_safe_logs(logs)
