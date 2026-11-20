"""Telegram polling logs must not expose exception payloads."""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.core.telegram import polling_manager


class _SecretConflictError(Exception):
    pass


class _SecretNetworkError(Exception):
    pass


class _FakeApplication:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


@pytest.mark.parametrize(
    ("error", "conflict", "transient", "expected_level"),
    [
        (_SecretConflictError("409 token=top-secret"), True, False, "ERROR"),
        (_SecretNetworkError("timeout api_key=top-secret"), False, True, "WARNING"),
    ],
)
def test_application_error_handler_redacts_exception_payload(
    error, conflict, transient, expected_level, monkeypatch, caplog
):
    app = _FakeApplication()
    monkeypatch.setattr(
        polling_manager, "is_telegram_conflict_error", lambda message: conflict
    )
    monkeypatch.setattr(
        polling_manager, "is_transient_telegram_network_error", lambda exc: transient
    )

    with caplog.at_level(logging.WARNING):
        asyncio.run(
            polling_manager._on_error(
                None, SimpleNamespace(error=error, application=app)
            )
        )

    assert "top-secret" not in caplog.text
    assert type(error).__name__ in caplog.text
    assert any(record.levelname == expected_level for record in caplog.records)
    assert app.stopped is conflict


def test_unhandled_application_error_does_not_log_traceback_or_message(
    monkeypatch, caplog
):
    error = RuntimeError("password=top-secret; https://api.example/botTOKEN/send")
    monkeypatch.setattr(
        polling_manager, "is_telegram_conflict_error", lambda message: False
    )
    monkeypatch.setattr(
        polling_manager, "is_transient_telegram_network_error", lambda exc: False
    )

    with caplog.at_level(logging.ERROR):
        asyncio.run(
            polling_manager._on_error(
                None, SimpleNamespace(error=error, application=_FakeApplication())
            )
        )

    assert "top-secret" not in caplog.text
    assert "api.example" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "Traceback" not in caplog.text
