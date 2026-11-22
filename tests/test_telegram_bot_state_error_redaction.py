"""Telegram 状态探测不得把 PTB/HTTPX 异常正文透传到管理端。"""
from app.core.telegram import bot_state
from app.core.config import settings


def test_probe_error_does_not_expose_exception_message_or_bot_api_url(monkeypatch):
    from app.core.telegram import ptb_runtime

    monkeypatch.setattr(bot_state, "bot_initialized", True)
    monkeypatch.setattr(bot_state, "TELEBOT_AVAILABLE", True)
    monkeypatch.setattr(settings, "TELEGRAM_TOKEN", "configured-token", raising=False)
    monkeypatch.setattr(
        ptb_runtime,
        "get_send_bot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("401 Unauthorized https://api.telegram.org/bot123456:SECRET_TOKEN/getMe")
        ),
    )

    result = bot_state._probe_telegram_connection()

    assert result == "失败（RuntimeError）"
    assert "SECRET_TOKEN" not in result
    assert "api.telegram.org" not in result
