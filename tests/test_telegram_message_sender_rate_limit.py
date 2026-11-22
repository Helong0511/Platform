# -*- coding: utf-8 -*-
"""Telegram message_sender 限流 / 429 共享退避 / 互斥锁单测。"""
from __future__ import annotations

import time
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.telegram import message_sender as ms
from app.core.config import settings


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, tuple[str, float]] = {}

    def _purge(self):
        now = time.monotonic()
        expired = [k for k, (_, exp) in self.store.items() if exp <= now]
        for k in expired:
            self.store.pop(k, None)

    def ping(self):
        return True

    def setex(self, key, seconds, value):
        self.store[key] = (str(value), time.monotonic() + float(seconds))

    def set(self, key, value, nx=False, px=None, ex=None):
        self._purge()
        now = time.monotonic()
        if nx and key in self.store and self.store[key][1] > now:
            return False
        ttl = 0.0
        if px is not None:
            ttl = float(px) / 1000.0
        elif ex is not None:
            ttl = float(ex)
        self.store[key] = (str(value), now + max(ttl, 0.001))
        return True

    def get(self, key):
        self._purge()
        item = self.store.get(key)
        return item[0] if item else None

    def expire(self, key, seconds):
        self._purge()
        item = self.store.get(key)
        if not item:
            return False
        self.store[key] = (item[0], time.monotonic() + float(seconds))
        return True

    def pttl(self, key):
        self._purge()
        item = self.store.get(key)
        if not item:
            return -2
        remain = item[1] - time.monotonic()
        if remain <= 0:
            self.store.pop(key, None)
            return -2
        return int(remain * 1000)

    def eval(self, script, numkeys, *keys_and_args):
        key = keys_and_args[0]
        token = keys_and_args[1]
        item = self.store.get(key)
        if item and item[0] == token:
            self.store.pop(key, None)
            return 1
        return 0


@pytest.fixture(autouse=True)
def _reset_sender_state():
    ms._sync_redis_client = None
    ms._sync_redis_failed_until = 0.0
    ms._last_send_monotonic = 0.0
    ms._last_send_by_chat.clear()
    yield
    ms._sync_redis_client = None
    ms._sync_redis_failed_until = 0.0
    ms._last_send_by_chat.clear()


def test_parse_retry_after():
    assert ms._parse_retry_after("Too Many Requests: retry after 8") == 8
    assert ms._parse_retry_after("retry after 1") == 1
    assert ms._parse_retry_after("nope") is None


def test_rate_limit_seconds_supports_retry_after_timedelta():
    class _RetryAfterError(Exception):
        def __init__(self, retry_after):
            super().__init__("Flood control exceeded")
            self.retry_after = retry_after

    assert ms._rate_limit_seconds_from_exc(_RetryAfterError(8)) == 8
    assert ms._rate_limit_seconds_from_exc(_RetryAfterError(timedelta(seconds=8))) == 8
    assert ms._rate_limit_seconds_from_exc(_RetryAfterError(timedelta(milliseconds=1500))) == 2
    assert ms._rate_limit_seconds_from_exc(_RetryAfterError(timedelta(0))) == 1


def test_note_rate_limited_writes_shared_backoff():
    fake = _FakeRedis()
    with patch.object(ms, "_get_sync_redis", return_value=fake):
        ms._note_rate_limited("5312177749", 8)
    assert ms._REDIS_BACKOFF_GLOBAL in fake.store
    assert ms._REDIS_BACKOFF_CHAT.format(chat_id="5312177749") in fake.store
    assert fake.pttl(ms._REDIS_BACKOFF_GLOBAL) > 7000


def test_wait_before_send_honors_shared_backoff(monkeypatch):
    fake = _FakeRedis()
    fake.setex(ms._REDIS_BACKOFF_GLOBAL, 1, "1")
    slept = []

    def _sleep(sec):
        slept.append(sec)
        fake.store.clear()

    monkeypatch.setattr(ms.time, "sleep", _sleep)
    with patch.object(ms, "_get_sync_redis", return_value=fake):
        monkeypatch.setattr(ms, "MIN_SEND_INTERVAL", 0.01)
        monkeypatch.setattr(ms, "MIN_GLOBAL_SEND_INTERVAL", 0.0)
        ms._wait_before_send("5312177749")

    assert slept, "应因共享退避而 sleep"
    assert slept[0] >= 0.5


def test_wait_before_send_cross_process_chat_gate(monkeypatch):
    fake = _FakeRedis()
    slept = []

    def _sleep(sec):
        slept.append(sec)
        fake.store.clear()

    monkeypatch.setattr(ms.time, "sleep", _sleep)
    monkeypatch.setattr(ms, "MIN_SEND_INTERVAL", 1.0)
    monkeypatch.setattr(ms, "MIN_GLOBAL_SEND_INTERVAL", 0.01)

    # 直接模拟另一个 worker 已占用 per-chat 闸门，避免依赖两次调用之间
    # 的真实调度时间；本测试只验证跨进程闸门等待，不测试本地时间间隔。
    fake.setex(ms._REDIS_GATE_CHAT.format(chat_id="chat-a"), 1, "other-worker")

    with patch.object(ms, "_get_sync_redis", return_value=fake):
        ms._wait_before_send("chat-a")

    assert any(s >= 0.05 for s in slept)


def test_chat_gate_miss_with_zero_pttl_spins_briefly(monkeypatch):
    """抢占失败且 PTTL=0 时短睡再抢，禁止空转，也禁止睡满 MIN_SEND_INTERVAL。"""
    fake = _FakeRedis()
    chat_key = "chat-expire"
    gate_key = ms._REDIS_GATE_CHAT.format(chat_id=chat_key)
    global_key = ms._REDIS_GATE_GLOBAL
    slept = []
    state = {"chat_attempts": 0}

    def _sleep(sec):
        slept.append(sec)

    def _acquire2(redis_client, key, interval_seconds):
        if key == global_key:
            return True
        if key == gate_key:
            state["chat_attempts"] += 1
            if state["chat_attempts"] == 1:
                return False
            return True
        return True

    def _wait_seconds(redis_client, key):
        return 0.0

    monkeypatch.setattr(ms.time, "sleep", _sleep)
    monkeypatch.setattr(ms, "MIN_SEND_INTERVAL", 1.1)
    monkeypatch.setattr(ms, "MIN_GLOBAL_SEND_INTERVAL", 0.0)
    monkeypatch.setattr(ms, "_try_acquire_redis_gate", _acquire2)
    monkeypatch.setattr(ms, "_redis_wait_seconds", _wait_seconds)

    with patch.object(ms, "_get_sync_redis", return_value=fake):
        ms._wait_before_send(chat_key)

    assert state["chat_attempts"] >= 2
    assert slept, "PTTL=0 时应短睡而非空转"
    assert all(s < 1.0 for s in slept), f"不应睡满 MIN_SEND_INTERVAL，实际 slept={slept}"


def test_send_mutex_serializes_and_releases():
    fake = _FakeRedis()
    with patch.object(ms, "_get_sync_redis", return_value=fake):
        token = ms._acquire_send_mutex(timeout=2.0)
        assert token
        assert fake.get(ms._REDIS_SEND_MUTEX) == token
        # 已被占用时短超时拿不到
        with patch.object(ms, "_sleep_with_jitter", lambda *a, **k: None):
            assert ms._acquire_send_mutex(timeout=0.01) is None
        ms._release_send_mutex(token)
        assert fake.get(ms._REDIS_SEND_MUTEX) is None


def test_estimate_timeout_covers_rate_limit_budget():
    assert ms.estimate_telegram_send_timeout_seconds(1) >= ms.MAX_RATE_LIMIT_WAIT



def test_sync_redis_uses_url_with_acl_tls_db_and_password_override(monkeypatch):
    calls = {}

    class _FakeClient:
        def ping(self):
            return True

    class _FakeRedis:
        @staticmethod
        def from_url(url, **kwargs):
            calls["url"] = url
            calls["kwargs"] = kwargs
            return _FakeClient()

    monkeypatch.setattr(settings, "REDIS_HOST", None, raising=False)
    monkeypatch.setattr(
        settings,
        "REDIS_URL",
        "rediss://telegram-user:url-secret@redis.example:6380/4",
        raising=False,
    )
    monkeypatch.setattr(settings, "REDIS_PASSWORD", "explicit-secret", raising=False)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=_FakeRedis))

    client = ms._get_sync_redis()

    assert isinstance(client, _FakeClient)
    assert calls["url"] == "rediss://telegram-user:url-secret@redis.example:6380/4"
    assert calls["kwargs"]["password"] == "explicit-secret"
    assert calls["kwargs"]["decode_responses"] is True
    assert calls["kwargs"]["socket_connect_timeout"] == 1.0


def test_sync_redis_preserves_url_password_when_no_override(monkeypatch):
    calls = {}

    class _FakeClient:
        def ping(self):
            return True

    class _FakeRedis:
        @staticmethod
        def from_url(url, **kwargs):
            calls["url"] = url
            calls["kwargs"] = kwargs
            return _FakeClient()

    monkeypatch.setattr(settings, "REDIS_HOST", None, raising=False)
    monkeypatch.setattr(
        settings,
        "REDIS_URL",
        "redis://acl-user:url-secret@redis.example:6379/3",
        raising=False,
    )
    monkeypatch.setattr(settings, "REDIS_PASSWORD", None, raising=False)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=_FakeRedis))

    assert isinstance(ms._get_sync_redis(), _FakeClient)
    assert "password" not in calls["kwargs"]



def test_group_chat_uses_telegram_twenty_per_minute_limit(monkeypatch):
    monkeypatch.setattr(ms, "MIN_SEND_INTERVAL", 1.1)
    monkeypatch.setattr(ms, "MIN_GROUP_SEND_INTERVAL", 3.1)

    assert ms._chat_send_interval("123456789") == 1.1
    assert ms._chat_send_interval("-1001234567890") == 3.1
    assert ms._chat_send_interval("-123456") == 3.1
    assert ms._chat_send_interval(None) == 1.1


def test_wait_before_send_applies_group_interval_to_redis_gate(monkeypatch):
    fake = _FakeRedis()
    observed = []
    monkeypatch.setattr(ms, "MIN_SEND_INTERVAL", 1.1)
    monkeypatch.setattr(ms, "MIN_GROUP_SEND_INTERVAL", 3.1)
    monkeypatch.setattr(ms, "MIN_GLOBAL_SEND_INTERVAL", 0.0)
    monkeypatch.setattr(ms, "_redis_wait_seconds", lambda *_args: 0.0)
    monkeypatch.setattr(
        ms,
        "_try_acquire_redis_gate",
        lambda _redis, key, interval: observed.append((key, interval)) or True,
    )

    with patch.object(ms, "_get_sync_redis", return_value=fake):
        ms._wait_before_send("-1001234567890")

    group_gate = ms._REDIS_GATE_CHAT.format(chat_id="-1001234567890")
    assert (group_gate, 3.1) in observed



def test_note_rate_limited_preserves_server_retry_after_above_inline_budget(monkeypatch):
    calls = []

    class _FakeRedis:
        def setex(self, key, seconds, value):
            calls.append((key, seconds, value))

    monkeypatch.setattr(ms, "_get_sync_redis", lambda: _FakeRedis())

    ms._note_rate_limited("-1001234567890", 300)

    assert (ms._REDIS_BACKOFF_GLOBAL, 300, "1") in calls
    assert (
        ms._REDIS_BACKOFF_CHAT.format(chat_id="-1001234567890"),
        300,
        "1",
    ) in calls


def test_send_message_does_not_retry_before_long_retry_after(monkeypatch):
    from datetime import timedelta
    from types import SimpleNamespace

    calls = []
    noted = []
    released = []

    class _RetryAfterError(Exception):
        def __init__(self):
            super().__init__("Flood control exceeded")
            self.retry_after = timedelta(seconds=300)

    class _FakeBot:
        def send_message(self, **_kwargs):
            calls.append("send")
            return object()

    monkeypatch.setattr(ms, "settings", SimpleNamespace(TELEGRAM_ENABLE=True))
    monkeypatch.setattr(ms, "_check_bot_available", lambda: (True, "ok"))
    monkeypatch.setattr(ms, "_get_send_bot", lambda: _FakeBot())
    monkeypatch.setattr(ms, "_acquire_send_mutex", lambda: "mutex-token")
    monkeypatch.setattr(ms, "_wait_before_send", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ms, "_sync_bot_call", lambda *_args, **_kwargs: (_ for _ in ()).throw(_RetryAfterError()))
    monkeypatch.setattr(ms, "_note_rate_limited", lambda chat_id, seconds: noted.append((chat_id, seconds)))
    monkeypatch.setattr(ms, "_release_send_mutex", lambda token: released.append(token))
    monkeypatch.setattr(
        ms,
        "_sleep_with_jitter",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not sleep/retry early")),
    )

    ok, error = ms.send_telegram_message_result(
        "123456789,987654321",
        "test message",
    )

    assert ok is False
    assert "超过当前请求预算" in error
    assert calls == ["send"]
    assert noted == [("123456789", 300)]
    assert released == ["mutex-token"]



def test_send_message_with_buttons_does_not_retry_before_long_retry_after(monkeypatch):
    from datetime import timedelta
    from types import SimpleNamespace

    calls = []
    noted = []
    released = []

    class _RetryAfterError(Exception):
        def __init__(self):
            super().__init__("Flood control exceeded")
            self.retry_after = timedelta(seconds=300)

    class _FakeBot:
        def send_message(self, **_kwargs):
            calls.append("send")
            return object()

    monkeypatch.setattr(ms, "settings", SimpleNamespace(TELEGRAM_ENABLE=True))
    monkeypatch.setattr(ms, "_check_bot_available", lambda: (True, "ok"))
    monkeypatch.setattr(ms, "_get_send_bot", lambda: _FakeBot())
    monkeypatch.setattr(ms, "_acquire_send_mutex", lambda: "mutex-token")
    monkeypatch.setattr(ms, "_wait_before_send", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ms, "_sync_bot_call", lambda *_args, **_kwargs: (_ for _ in ()).throw(_RetryAfterError()))
    monkeypatch.setattr(ms, "_note_rate_limited", lambda chat_id, seconds: noted.append((chat_id, seconds)))
    monkeypatch.setattr(ms, "_release_send_mutex", lambda token: released.append(token))
    monkeypatch.setattr(
        ms,
        "_sleep_with_jitter",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not sleep/retry early")),
    )

    ok, message_id = ms.send_telegram_message_with_buttons(
        "123456789",
        "test message",
        [[{"text": "Approve", "callback_data": "approve_1"}]],
    )

    assert ok is False
    assert message_id is None
    assert calls == ["send"]
    assert noted == [("123456789", 300)]
    assert released == ["mutex-token"]



def test_chat_target_log_category_never_returns_raw_identifier():
    assert ms._chat_target_type_for_log("-1001234567890") == "group_or_channel"
    assert ms._chat_target_type_for_log("123456789") == "private_user"
    assert ms._chat_target_type_for_log("@admin_channel") == "unknown"


def test_send_message_logs_do_not_expose_chat_id(monkeypatch, caplog):
    import logging
    from types import SimpleNamespace

    secret_chat_id = "-1001234567890"

    class _FakeBot:
        def send_message(self, **_kwargs):
            return object()

    monkeypatch.setattr(ms, "settings", SimpleNamespace(TELEGRAM_ENABLE=True))
    monkeypatch.setattr(ms, "_check_bot_available", lambda: (True, "ok"))
    monkeypatch.setattr(ms, "_get_send_bot", lambda: _FakeBot())
    monkeypatch.setattr(ms, "_acquire_send_mutex", lambda: "mutex-token")
    monkeypatch.setattr(ms, "_wait_before_send", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ms, "_sync_bot_call", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(ms, "_release_send_mutex", lambda _token: None)

    with caplog.at_level(logging.INFO, logger=ms.logger.name):
        ok, _error = ms.send_telegram_message_result(secret_chat_id, "test")

    assert ok is True
    assert secret_chat_id not in caplog.text
    assert "target_type=group_or_channel" in caplog.text


def test_button_message_logs_do_not_expose_chat_id(monkeypatch, caplog):
    import logging
    from types import SimpleNamespace
    from app.core.telegram import ptb_runtime

    secret_chat_id = "-1009876543210"

    class _FakeBot:
        def send_message(self, **_kwargs):
            return object()

    monkeypatch.setattr(ms, "_check_bot_available", lambda: (True, "ok"))
    monkeypatch.setattr(ms, "_get_send_bot", lambda: _FakeBot())
    monkeypatch.setattr(ptb_runtime, "build_inline_keyboard", lambda _buttons: "markup")
    monkeypatch.setattr(ms, "_acquire_send_mutex", lambda: "mutex-token")
    monkeypatch.setattr(ms, "_wait_before_send", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ms,
        "_sync_bot_call",
        lambda *_args, **_kwargs: SimpleNamespace(message_id=123),
    )
    monkeypatch.setattr(ms, "_release_send_mutex", lambda _token: None)

    with caplog.at_level(logging.INFO, logger=ms.logger.name):
        ok, message_id = ms.send_telegram_message_with_buttons(
            secret_chat_id,
            "test",
            [[{"text": "Approve", "callback_data": "approve_1"}]],
        )

    assert ok is True
    assert message_id == 123
    assert secret_chat_id not in caplog.text
    assert "target_type=group_or_channel" in caplog.text


def test_invalid_button_chat_id_is_not_written_to_logs(monkeypatch, caplog):
    import logging

    secret_invalid_id = "private-chat-id-do-not-log"
    monkeypatch.setattr(ms, "_check_bot_available", lambda: (True, "ok"))

    with caplog.at_level(logging.WARNING, logger=ms.logger.name):
        ok, message_id = ms.send_telegram_message_with_buttons(
            secret_invalid_id,
            "test",
            [[{"text": "Approve", "callback_data": "approve_1"}]],
        )

    assert ok is False
    assert message_id is None
    assert secret_invalid_id not in caplog.text
    assert "target_type=unknown" in caplog.text
