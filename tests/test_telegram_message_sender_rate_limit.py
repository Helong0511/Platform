# -*- coding: utf-8 -*-
"""Telegram message_sender 限流 / 429 共享退避单测。"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.core.telegram import message_sender as ms


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, tuple[str, float]] = {}

    def ping(self):
        return True

    def setex(self, key, seconds, value):
        self.store[key] = (str(value), time.monotonic() + float(seconds))

    def set(self, key, value, nx=False, px=None, ex=None):
        now = time.monotonic()
        expired = [k for k, (_, exp) in self.store.items() if exp <= now]
        for k in expired:
            self.store.pop(k, None)
        if nx and key in self.store and self.store[key][1] > now:
            return False
        ttl = 0.0
        if px is not None:
            ttl = float(px) / 1000.0
        elif ex is not None:
            ttl = float(ex)
        self.store[key] = (str(value), now + max(ttl, 0.001))
        return True

    def pttl(self, key):
        now = time.monotonic()
        item = self.store.get(key)
        if not item:
            return -2
        _, exp = item
        remain = exp - now
        if remain <= 0:
            self.store.pop(key, None)
            return -2
        return int(remain * 1000)


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

    with patch.object(ms, "_get_sync_redis", return_value=fake):
        ms._wait_before_send("chat-a")
        ms._last_send_by_chat.clear()
        ms._last_send_monotonic = 0.0
        ms._wait_before_send("chat-a")

    assert any(s >= 0.05 for s in slept)


def test_chat_gate_miss_with_zero_pttl_retries_immediately(monkeypatch):
    """
    抢占失败且 PTTL=0（闸门刚过期）时，应立刻重试，而不是 sleep(MIN_SEND_INTERVAL)。
    """
    fake = _FakeRedis()
    chat_key = "chat-expire"
    gate_key = ms._REDIS_GATE_CHAT.format(chat_id=chat_key)
    global_key = ms._REDIS_GATE_GLOBAL
    slept = []
    acquire_calls = {"n": 0}

    def _sleep(sec):
        slept.append(sec)

    real_acquire = ms._try_acquire_redis_gate

    def _acquire(redis_client, key, interval_seconds):
        acquire_calls["n"] += 1
        # 第一次 chat 闸门故意失败，随后 pttl 返回 0；第二次应成功
        if key == gate_key and acquire_calls["n"] <= 2:
            # call 1 = global ok path... actually order: global then chat
            pass
        if key == gate_key and acquire_calls["n"] == 2:
            # 第一次尝试 chat：失败
            return False
        return real_acquire(redis_client, key, interval_seconds)

    # 更精确：控制前两次 chat 失败一次
    state = {"chat_attempts": 0}

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
        if key == gate_key:
            return 0.0  # 闸门已过期
        return 0.0

    monkeypatch.setattr(ms.time, "sleep", _sleep)
    monkeypatch.setattr(ms, "MIN_SEND_INTERVAL", 1.1)
    monkeypatch.setattr(ms, "MIN_GLOBAL_SEND_INTERVAL", 0.0)
    monkeypatch.setattr(ms, "_try_acquire_redis_gate", _acquire2)
    monkeypatch.setattr(ms, "_redis_wait_seconds", _wait_seconds)

    with patch.object(ms, "_get_sync_redis", return_value=fake):
        ms._wait_before_send(chat_key)

    assert state["chat_attempts"] >= 2, "PTTL=0 时应立刻再抢一次 chat 闸门"
    assert not any(s >= 1.0 for s in slept), f"不应睡满 MIN_SEND_INTERVAL，实际 slept={slept}"


def test_estimate_timeout_covers_rate_limit_budget():
    assert ms.estimate_telegram_send_timeout_seconds(1) >= ms.MAX_RATE_LIMIT_WAIT
