# -*- coding: utf-8 -*-
"""TELEGRAM_ENABLE=false 时全部发送入口应短路。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.telegram import message_sender as ms


@pytest.fixture(autouse=True)
def _disable_telegram(monkeypatch):
    monkeypatch.setattr(ms.settings, "TELEGRAM_ENABLE", False)


def test_is_telegram_enabled_false():
    assert ms.is_telegram_enabled() is False


def test_send_telegram_message_skipped_when_disabled():
    # 当前发送入口先检查全局开关，不应初始化 Bot 或访问 Telegram 网络。
    with patch.object(ms, "_check_bot_available") as check:
        ok = ms.send_telegram_message("hello")
    assert ok is False
    check.assert_not_called()


def test_send_with_buttons_skipped_when_disabled():
    with patch.object(ms, "_check_bot_available") as check:
        ok, mid = ms.send_telegram_message_with_buttons("1", "hi", [[{"text": "a", "callback_data": "b"}]])
    assert ok is False
    assert mid is None
    check.assert_not_called()


@pytest.mark.asyncio
async def test_notify_async_skipped_when_disabled():
    with patch.object(ms, "send_telegram_message_async") as send_async:
        ok = await ms.send_telegram_notify_async("1", "hi")
    assert ok is False
    send_async.assert_not_called()


def test_check_bot_available_reports_disabled():
    ok, msg = ms._check_bot_available()
    assert ok is False
    assert "TELEGRAM_ENABLE=false" in msg
