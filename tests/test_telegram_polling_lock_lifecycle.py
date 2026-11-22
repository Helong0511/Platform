"""Polling startup failures must release the OS lock and reset local state."""

from types import SimpleNamespace

import pytest

from app.core.telegram import polling_manager as manager
from app.core.telegram import ptb_runtime


@pytest.mark.parametrize("failure_stage", ["application_build", "handler_registration", "bot_state"])
def test_startup_failure_always_releases_lock_and_clears_state(
    failure_stage, monkeypatch
):
    released = []
    shared_states = []
    bot_state_calls = []

    monkeypatch.setattr(manager, "_bot_started", False)
    monkeypatch.setattr(manager, "_active_application", None)
    monkeypatch.setattr(manager, "_polling_loop", None)
    monkeypatch.setattr(manager, "is_bot_running", lambda: False)
    monkeypatch.setattr(manager, "acquire_bot_lock", lambda: True)
    monkeypatch.setattr(manager, "release_bot_lock", lambda: released.append(True))
    monkeypatch.setattr(manager, "set_shared_state", lambda state: shared_states.append(state.copy()))
    monkeypatch.setattr(manager.time, "sleep", lambda *_args: None)
    monkeypatch.setattr(manager, "PTB_AVAILABLE", True)
    monkeypatch.setattr(manager.settings, "TELEGRAM_ENABLE", True)
    monkeypatch.setattr(manager.settings, "TELEGRAM_TOKEN", "test-token")

    # Token 探测失败会被既有兼容逻辑捕获，随后继续构建轮询 Application；
    # 这样可分别注入 Application、Handler、bot_state 阶段的异常。
    monkeypatch.setattr(
        ptb_runtime,
        "get_send_bot",
        lambda _token: (_ for _ in ()).throw(RuntimeError("synthetic probe failure")),
    )

    class FakeApplication:
        bot = object()

        def add_error_handler(self, _handler):
            return None

    if failure_stage == "application_build":
        monkeypatch.setattr(
            manager,
            "_build_polling_application",
            lambda _token: (_ for _ in ()).throw(RuntimeError("synthetic build failure")),
        )
    else:
        monkeypatch.setattr(manager, "_build_polling_application", lambda _token: FakeApplication())

    if failure_stage == "handler_registration":
        monkeypatch.setattr(
            manager,
            "register_handlers",
            lambda _app: (_ for _ in ()).throw(RuntimeError("synthetic handler failure")),
        )
    else:
        monkeypatch.setattr(manager, "register_handlers", lambda _app: None)

    from app.core.telegram import bot_state

    def set_bot_state(*_args, **_kwargs):
        bot_state_calls.append(True)
        if failure_stage == "bot_state":
            raise RuntimeError("synthetic bot state failure")

    monkeypatch.setattr(bot_state, "set_bot_state", set_bot_state)

    with pytest.raises(RuntimeError):
        manager.start_polling()

    assert released == [True]
    assert manager._bot_started is False
    assert manager._active_application is None
    assert manager._polling_loop is None
    assert shared_states[-1] == {
        "bot_initialized": True,
        "bot_running": False,
        "current_pid": None,
        "last_start_time": None,
        "bot_username": None,
    }
    assert bot_state_calls, "finally 必须尝试清理 PTB bot_state"
