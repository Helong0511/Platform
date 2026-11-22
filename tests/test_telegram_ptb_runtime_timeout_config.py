"""发送 Bot 作为进程级单例时必须使用统一 HTTPX 超时，避免初始化入口污染正式发送。"""
import asyncio

from app.core.telegram import ptb_runtime


def test_send_bot_uses_centralized_http_timeouts(monkeypatch):
    captured = {}

    class FakeBot:
        pass

    async def fake_create_send_bot(token):
        captured["token"] = token
        captured["connect_timeout"] = ptb_runtime.SEND_BOT_CONNECT_TIMEOUT_SECONDS
        captured["read_timeout"] = ptb_runtime.SEND_BOT_READ_TIMEOUT_SECONDS
        return FakeBot()

    def fake_run_on_send_loop(coro, *, timeout=None):
        captured["initialization_timeout"] = timeout
        return asyncio.run(coro)

    monkeypatch.setattr(ptb_runtime, "_send_bot", None)
    monkeypatch.setattr(ptb_runtime, "_send_bot_token", None)
    monkeypatch.setattr(ptb_runtime, "_create_send_bot", fake_create_send_bot)
    monkeypatch.setattr(ptb_runtime, "run_on_send_loop", fake_run_on_send_loop)

    bot = ptb_runtime.get_send_bot("test-token")

    assert isinstance(bot, FakeBot)
    assert captured == {
        "token": "test-token",
        "connect_timeout": 3.0,
        "read_timeout": 30.0,
        "initialization_timeout": 33.0,
    }
