"""Telegram polling supervisor 的退避、熔断和健康心跳测试。"""
import asyncio
import threading
import time
from types import SimpleNamespace

from app.core.telegram import polling_exception_handler, polling_manager as manager


def _run_supervisor_and_join(monkeypatch, fake_start):
    monkeypatch.setattr(manager, "_check_bot_ready_for_polling", lambda: True)
    monkeypatch.setattr(manager, "start_polling", fake_start)
    monkeypatch.setattr(manager, "POLLING_SUPERVISOR_BASE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(manager, "POLLING_SUPERVISOR_MAX_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(manager, "POLLING_SUPERVISOR_JITTER_SECONDS", 0.0)
    entered = threading.Event()
    continue_run = threading.Event()

    def controlled_start():
        entered.set()
        assert continue_run.wait(timeout=2.0)
        fake_start()

    monkeypatch.setattr(manager, "start_polling", controlled_start)
    assert manager.start_bot_thread() is True
    assert entered.wait(timeout=2.0)
    thread = next(
        (item for item in threading.enumerate() if item.name == "TelegramBot"),
        None,
    )
    assert thread is not None
    continue_run.set()
    thread.join(timeout=3.0)
    assert not thread.is_alive()


def test_supervisor_retries_transient_bootstrap_failures_with_bounded_attempts(monkeypatch):
    reasons = ["transient_network_error", "transient_network_error", "stopped"]
    calls = []
    alerts = []

    def fake_start():
        calls.append(True)
        manager._last_polling_exit_reason = reasons.pop(0)
        if manager._last_polling_exit_reason == "stopped":
            manager._supervisor_stop_event.set()

    monkeypatch.setattr(manager, "_notify_supervisor_failure", alerts.append)
    _run_supervisor_and_join(monkeypatch, fake_start)

    assert len(calls) == 3
    assert manager._supervisor_restart_count == 2
    assert alerts == []
    assert manager.get_polling_health_status()["supervisor_running"] is False


def test_supervisor_does_not_restart_after_409_conflict(monkeypatch):
    calls = []
    alerts = []

    def fake_start():
        calls.append(True)
        manager._last_polling_exit_reason = "conflict"

    monkeypatch.setattr(manager, "_notify_supervisor_failure", alerts.append)
    _run_supervisor_and_join(monkeypatch, fake_start)

    assert len(calls) == 1
    assert alerts == ["conflict"]


def test_supervisor_opens_circuit_after_maximum_transient_restarts(monkeypatch):
    calls = []
    alerts = []

    def fake_start():
        calls.append(True)
        manager._last_polling_exit_reason = "transient_network_error"

    monkeypatch.setattr(manager, "POLLING_SUPERVISOR_MAX_RESTARTS", 2)
    monkeypatch.setattr(manager, "_notify_supervisor_failure", alerts.append)
    _run_supervisor_and_join(monkeypatch, fake_start)

    assert len(calls) == 3
    assert alerts == ["maximum restart attempts reached"]


def test_supervisor_does_not_retry_permanent_authentication_failure(monkeypatch):
    calls = []
    alerts = []

    def fake_start():
        calls.append(True)
        manager._last_polling_exit_reason = "permanent_auth_error"

    monkeypatch.setattr(manager, "_notify_supervisor_failure", alerts.append)
    _run_supervisor_and_join(monkeypatch, fake_start)

    assert len(calls) == 1
    assert alerts == ["permanent_auth_error"]


def test_permanent_telegram_auth_error_is_classified_without_message_leak():
    class UnauthorizedError(Exception):
        error_code = 401

    assert polling_exception_handler.is_permanent_telegram_auth_error(
        UnauthorizedError("credential rejected")
    ) is True
    assert polling_exception_handler.is_permanent_telegram_auth_error(
        TimeoutError("network timeout")
    ) is False


def test_get_updates_instrumentation_records_success_heartbeat():
    class FakeBot:
        async def get_updates(self):
            return []

    application = SimpleNamespace(bot=FakeBot())
    manager._last_get_updates_success_at = None
    manager._instrument_get_updates(application)

    assert asyncio.run(application.bot.get_updates()) == []
    assert manager._last_get_updates_success_at is not None


def test_update_handler_records_last_received_update():
    manager._last_update_received_at = None

    asyncio.run(manager._record_update_received(object(), object()))

    assert manager._last_update_received_at is not None


def test_polling_error_handler_marks_conflict_as_terminal():
    class FakeApplication:
        def __init__(self):
            self.stopped = False

        def stop_running(self):
            self.stopped = True

    app = FakeApplication()
    error = RuntimeError("Conflict: terminated by other getUpdates request")
    context = SimpleNamespace(error=error, application=app)

    asyncio.run(manager._on_error(None, context))

    assert app.stopped is True
    assert manager._last_polling_exit_reason == "conflict"
