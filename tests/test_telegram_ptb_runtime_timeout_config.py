"""发送 Bot 作为进程级单例时必须使用统一 HTTPX 超时，避免初始化入口污染正式发送。"""
import asyncio
import sys
from types import ModuleType

from app.core.telegram import ptb_runtime


def test_send_bot_uses_centralized_http_timeouts(monkeypatch):
    captured = {}

    class FakeHTTPXRequest:
        def __init__(self, **kwargs):
            captured["request_kwargs"] = kwargs

    class FakeBot:
        def __init__(self, token, request):
            captured["token"] = token
            self.request = request

        async def initialize(self):
            captured["initialized"] = True

    telegram_module = ModuleType("telegram")
    telegram_module.Bot = FakeBot
    request_module = ModuleType("telegram.request")
    request_module.HTTPXRequest = FakeHTTPXRequest
    telegram_module.request = request_module

    monkeypatch.setitem(sys.modules, "telegram", telegram_module)
    monkeypatch.setitem(sys.modules, "telegram.request", request_module)
    monkeypatch.setattr(ptb_runtime, "_send_bot", None)
    monkeypatch.setattr(ptb_runtime, "_send_bot_token", None)

    def fake_run_on_send_loop(coro, *, timeout=None):
        captured["initialization_timeout"] = timeout
        return asyncio.run(coro)

    monkeypatch.setattr(ptb_runtime, "run_on_send_loop", fake_run_on_send_loop)

    bot = ptb_runtime.get_send_bot("test-token")

    assert isinstance(bot, FakeBot)
    assert captured["token"] == "test-token"
    assert captured["initialized"] is True
    assert captured["request_kwargs"] == {
        "connect_timeout": 3.0,
        "read_timeout": 30.0,
        "write_timeout": 30.0,
    }
    assert captured["initialization_timeout"] == 33.0
