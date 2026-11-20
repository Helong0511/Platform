"""Telegram 兼容异常处理和告警发送日志不得泄露异常正文。"""
import logging

from app.core.telegram import polling_exception_handler, runtime_error_notify


class _SecretError(RuntimeError):
    pass


def test_legacy_polling_handler_redacts_conflict_and_callback_errors(monkeypatch, caplog):
    secret = "token=super-secret https://api.example/bot-secret"
    error = _SecretError(f"409 Conflict {secret}")
    monkeypatch.setattr(
        polling_exception_handler,
        "is_telegram_conflict_error",
        lambda message: "409" in message,
    )

    def fail_callback(_exception):
        raise _SecretError(secret)

    handler = polling_exception_handler.TelegramPollingExceptionHandler(
        on_conflict=fail_callback
    )
    with caplog.at_level(logging.WARNING):
        assert handler.handle(error) is True

    assert handler.conflict_detected is True
    assert "_SecretError" in caplog.text
    assert "super-secret" not in caplog.text
    assert "api.example" not in caplog.text


def test_legacy_polling_handler_redacts_transient_error(monkeypatch, caplog):
    error = _SecretError("timeout token=super-secret")
    monkeypatch.setattr(
        polling_exception_handler, "is_telegram_conflict_error", lambda _message: False
    )
    monkeypatch.setattr(
        polling_exception_handler,
        "is_transient_telegram_network_error",
        lambda _exception: True,
    )

    handler = polling_exception_handler.TelegramPollingExceptionHandler()
    with caplog.at_level(logging.WARNING):
        assert handler.handle(error) is True

    assert "_SecretError" in caplog.text
    assert "super-secret" not in caplog.text


def test_runtime_alert_send_failure_logs_only_exception_type(monkeypatch, caplog):
    from app.core.telegram import message_sender

    secret = "password=super-secret https://api.example/bot-secret"
    monkeypatch.setattr(
        message_sender,
        "send_telegram_message",
        lambda _message: (_ for _ in ()).throw(_SecretError(secret)),
    )

    with caplog.at_level(logging.WARNING):
        runtime_error_notify._send_sync("safe notification")

    assert "_SecretError" in caplog.text
    assert "super-secret" not in caplog.text
    assert "api.example" not in caplog.text
