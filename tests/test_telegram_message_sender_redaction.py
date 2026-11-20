"""Telegram 发送异常日志和对外失败原因不得泄露 API 响应正文、Token 或 URL。"""
import logging

from app.core.telegram import message_sender


class _SecretTelegramError(RuntimeError):
    pass


class _FakeBot:
    def send_message(self, **_kwargs):
        return object()


def _prepare_sender(monkeypatch):
    monkeypatch.setattr(message_sender, "_check_bot_available", lambda: (True, "Bot 可用"))
    monkeypatch.setattr(message_sender, "_get_send_bot", lambda: _FakeBot())
    monkeypatch.setattr(message_sender, "_acquire_send_mutex", lambda: "")
    monkeypatch.setattr(message_sender, "_release_send_mutex", lambda _token: None)
    monkeypatch.setattr(message_sender, "_wait_before_send", lambda _chat_id: None)
    monkeypatch.setattr(message_sender, "MAX_RETRIES", 1)
    monkeypatch.setattr(
        message_sender,
        "_sync_bot_call",
        lambda _coro: (_ for _ in ()).throw(
            _SecretTelegramError("401 Unauthorized token=top-secret https://api.telegram.org/botTOPSECRET/sendMessage")
        ),
    )


def test_message_send_redacts_exception_from_logs_and_result(monkeypatch, caplog):
    _prepare_sender(monkeypatch)

    with caplog.at_level(logging.ERROR):
        success, reason = message_sender.send_telegram_message_result("123456", "hello")

    assert success is False
    assert "_SecretTelegramError" in caplog.text
    assert "top-secret" not in caplog.text
    assert "TOPSECRET" not in caplog.text
    assert "api.telegram.org" not in caplog.text
    assert "top-secret" not in reason
    assert "api.telegram.org" not in reason


def test_button_send_redacts_exception_from_logs(monkeypatch, caplog):
    _prepare_sender(monkeypatch)
    from app.core.telegram import ptb_runtime
    monkeypatch.setattr(ptb_runtime, "build_inline_keyboard", lambda _buttons: object())

    with caplog.at_level(logging.ERROR):
        success, message_id = message_sender.send_telegram_message_with_buttons(
            "123456", "hello", [[{"text": "OK", "callback_data": "ok"}]]
        )

    assert success is False
    assert message_id is None
    assert "_SecretTelegramError" in caplog.text
    assert "top-secret" not in caplog.text
    assert "TOPSECRET" not in caplog.text
    assert "api.telegram.org" not in caplog.text


def test_bot_availability_error_returns_only_safe_error_type(monkeypatch, caplog):
    from app.core.telegram import ptb_runtime
    from app.core.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_TOKEN", "configured-token", raising=False)
    monkeypatch.setattr(
        ptb_runtime,
        "get_send_bot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            _SecretTelegramError("token=top-secret https://api.telegram.org/botTOPSECRET")
        ),
    )

    with caplog.at_level(logging.WARNING):
        available, status = message_sender._check_bot_available()

    assert available is False
    assert status == "Bot 初始化失败"
    assert "top-secret" not in status
    assert "TOPSECRET" not in caplog.text
    assert "api.telegram.org" not in caplog.text
