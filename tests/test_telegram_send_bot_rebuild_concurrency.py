"""Concurrent send Bot rebuilds must never leak or prematurely close instances."""

import asyncio
import threading

import pytest

from app.core.telegram import ptb_runtime


class FakeBot:
    def __init__(self, token):
        self.token = token
        self.shutdown_count = 0

    async def shutdown(self):
        self.shutdown_count += 1


def _reset_send_bot_state(monkeypatch):
    monkeypatch.setattr(ptb_runtime, "_send_bot", None)
    monkeypatch.setattr(ptb_runtime, "_send_bot_token", None)
    monkeypatch.setattr(ptb_runtime, "_send_bot_lock", threading.Lock())
    monkeypatch.setattr(ptb_runtime, "_send_bot_rebuild_lock", threading.Lock())
    monkeypatch.setattr(
        ptb_runtime,
        "run_on_send_loop",
        lambda coro, *, timeout=None: asyncio.run(coro),
    )


def test_concurrent_same_token_builds_only_one_send_bot(monkeypatch):
    _reset_send_bot_state(monkeypatch)
    created = []
    created_lock = threading.Lock()

    async def create_bot(token):
        await asyncio.sleep(0.05)
        bot = FakeBot(token)
        with created_lock:
            created.append(bot)
        return bot

    monkeypatch.setattr(ptb_runtime, "_create_send_bot", create_bot)
    results = []
    errors = []

    def worker():
        try:
            results.append(ptb_runtime.get_send_bot("same-token"))
        except Exception as exc:  # pragma: no cover - assertion reports unexpected failure
            errors.append(exc)

    first = threading.Thread(target=worker)
    second = threading.Thread(target=worker)
    first.start()
    second.start()
    first.join(timeout=3)
    second.join(timeout=3)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert len(created) == 1
    assert len(results) == 2
    assert results[0] is results[1] is created[0]
    assert ptb_runtime._send_bot is created[0]
    assert ptb_runtime._send_bot_token == "same-token"


def test_concurrent_different_tokens_shutdown_old_before_publishing_new(monkeypatch):
    _reset_send_bot_state(monkeypatch)
    first_create_entered = threading.Event()
    allow_first_create = threading.Event()
    second_started = threading.Event()
    created = []
    results = {}

    async def create_bot(token):
        if token == "token-a":
            first_create_entered.set()
            await asyncio.to_thread(allow_first_create.wait, 2)
        bot = FakeBot(token)
        created.append(bot)
        return bot

    monkeypatch.setattr(ptb_runtime, "_create_send_bot", create_bot)

    def worker(key, token, started_event=None):
        if started_event is not None:
            started_event.set()
        results[key] = ptb_runtime.get_send_bot(token)

    first = threading.Thread(target=worker, args=("a", "token-a"))
    second = threading.Thread(
        target=worker, args=("b", "token-b", second_started)
    )
    first.start()
    assert first_create_entered.wait(timeout=2)
    second.start()
    assert second_started.wait(timeout=2)
    allow_first_create.set()
    first.join(timeout=3)
    second.join(timeout=3)

    assert not first.is_alive()
    assert not second.is_alive()
    assert results["a"].token == "token-a"
    assert results["b"].token == "token-b"
    assert results["a"].shutdown_count == 1
    assert results["b"].shutdown_count == 0
    assert ptb_runtime._send_bot is results["b"]
    assert ptb_runtime._send_bot_token == "token-b"
    assert len(created) == 2


def test_failed_rebuild_does_not_leave_shutdown_bot_in_cache(monkeypatch):
    _reset_send_bot_state(monkeypatch)
    old_bot = FakeBot("old-token")
    monkeypatch.setattr(ptb_runtime, "_send_bot", old_bot)
    monkeypatch.setattr(ptb_runtime, "_send_bot_token", "old-token")
    calls = 0

    async def create_bot(token):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic creation failure")
        return FakeBot(token)

    monkeypatch.setattr(ptb_runtime, "_create_send_bot", create_bot)

    with pytest.raises(RuntimeError):
        ptb_runtime.get_send_bot("new-token")

    assert old_bot.shutdown_count == 1
    assert ptb_runtime._send_bot is None
    assert ptb_runtime._send_bot_token is None

    new_bot = ptb_runtime.get_send_bot("new-token")
    assert new_bot.token == "new-token"
    assert ptb_runtime._send_bot is new_bot
