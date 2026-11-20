"""Telegram 锁文件、共享状态和命令回复日志必须脱敏异常正文。"""
from types import SimpleNamespace

from app.core.telegram.command_handlers import _reply_errors
from app.core.telegram import file_lock, shared_state


class _SecretTelegramError(RuntimeError):
    pass


def _assert_redacted(logs):
    rendered = repr(logs)
    assert "_SecretTelegramError" in rendered
    assert "private-password" not in rendered
    assert "botTOPSECRET" not in rendered
    assert "api.telegram.org" not in rendered


def test_command_reply_error_logs_only_error_type(monkeypatch):
    logs = []
    monkeypatch.setattr(_reply_errors.logger, "error", lambda *args, **_kwargs: logs.append(args))

    _reply_errors.log_command_reply_failure(
        "start",
        123456,
        _SecretTelegramError("chat not found token=private-password https://api.telegram.org/botTOPSECRET"),
    )
    _assert_redacted(logs)


def test_generic_command_reply_error_does_not_log_traceback(monkeypatch):
    logs = []
    monkeypatch.setattr(_reply_errors.logger, "error", lambda *args, **_kwargs: logs.append(args))

    _reply_errors.log_command_reply_failure(
        "help",
        123456,
        _SecretTelegramError("private-password https://api.telegram.org/botTOPSECRET"),
    )
    _assert_redacted(logs)
    assert all("exc_info" not in repr(item) for item in logs)


def test_lock_file_read_error_logs_only_error_type(monkeypatch):
    logs = []
    monkeypatch.setattr(file_lock.logger, "warning", lambda *args, **_kwargs: logs.append(args))
    monkeypatch.setattr(
        file_lock,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            _SecretTelegramError("private-password https://api.telegram.org/botTOPSECRET")
        ),
        raising=False,
    )
    path = SimpleNamespace(exists=lambda: True)

    assert file_lock._is_lock_expired(path) is False
    _assert_redacted(logs)


def test_shared_state_read_error_logs_only_error_type(monkeypatch):
    logs = []
    monkeypatch.setattr(shared_state.logger, "warning", lambda *args, **_kwargs: logs.append(args))
    monkeypatch.setattr(
        shared_state,
        "STATE_FILE",
        SimpleNamespace(exists=lambda: True),
    )
    monkeypatch.setattr(
        shared_state,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            _SecretTelegramError("private-password https://api.telegram.org/botTOPSECRET")
        ),
        raising=False,
    )

    state = shared_state.get_shared_state()
    assert state["bot_running"] is False
    _assert_redacted(logs)
