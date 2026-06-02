"""Telegram 轮询异常处理器测试。"""
from types import SimpleNamespace

from app.core.telegram.polling_exception_handler import (
    TelegramPollingExceptionHandler,
    is_telegram_conflict_error,
    is_transient_telegram_network_error,
)


def test_is_telegram_conflict_error():
    assert is_telegram_conflict_error("Error code: 409. Description: Conflict")
    assert is_telegram_conflict_error("terminated by other getUpdates request")
    assert not is_telegram_conflict_error("Error code: 502. Description: Bad Gateway")


def test_is_transient_telegram_network_error_by_code():
    exc = SimpleNamespace(error_code=502)
    assert is_transient_telegram_network_error(exc)


def test_is_transient_telegram_network_error_by_message():
    exc = Exception("HTTPSConnectionPool(host='api.telegram.org'): Read timed out.")
    assert is_transient_telegram_network_error(exc)


def test_conflict_is_not_transient_network_error():
    exc = Exception("Error code: 409. Description: Conflict")
    assert not is_transient_telegram_network_error(exc)


def test_handler_marks_transient_errors_as_handled():
    handler = TelegramPollingExceptionHandler()
    exc = SimpleNamespace(error_code=502)

    assert handler.handle(exc) is True
    assert handler.conflict_detected is False


def test_handler_stops_on_conflict():
    stopped = {"called": False}

    def on_conflict(exc):
        stopped["called"] = True

    handler = TelegramPollingExceptionHandler(on_conflict=on_conflict)
    exc = Exception("Error code: 409. Description: Conflict")

    assert handler.handle(exc) is True
    assert handler.conflict_detected is True
    assert stopped["called"] is True
