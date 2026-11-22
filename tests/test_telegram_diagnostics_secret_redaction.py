"""Telegram diagnostics must never print Bot Tokens, proxy credentials, or private chat IDs."""
from app.core.telegram import bot_diagnostics
from app.core.config import settings


def test_diagnostic_configuration_does_not_expose_token_or_chat_ids(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_TOKEN", "123456:TOP_SECRET_TOKEN", raising=False)
    monkeypatch.setattr(settings, "TELEGRAM_ADMIN", "123456789,-1001234567890", raising=False)
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "-1001234567890", raising=False)

    result = bot_diagnostics.TelegramBotDiagnostics._check_configuration()
    rendered = repr(result)

    assert result["telegram_token_configured"] is True
    assert result["telegram_admin_configured"] is True
    assert result["telegram_chat_id_configured"] is True
    assert "token_prefix" not in result
    assert "token_bot_id" not in result
    assert "admin_value" not in result
    assert "chat_id_value" not in result
    assert "TOP_SECRET_TOKEN" not in rendered
    assert "123456789" not in rendered
    assert "-1001234567890" not in rendered


def test_diagnostic_environment_variables_are_redacted(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "123456:TOP_SECRET_TOKEN")
    monkeypatch.setenv("TELEGRAM_ADMIN", "-1001234567890")
    monkeypatch.setenv("TELEGRAM_PROXY", "http://user:proxy-secret@proxy.example:8080")
    monkeypatch.setenv("TELEGRAM_ENABLE", "true")

    result = bot_diagnostics.TelegramBotDiagnostics._check_system()
    values = result["env_vars"]

    assert values["TELEGRAM_TOKEN"] == "[已设置]"
    assert values["TELEGRAM_ADMIN"] == "[已设置]"
    assert values["TELEGRAM_PROXY"] == "[已设置]"
    assert values["TELEGRAM_ENABLE"] == "true"
    rendered = repr(values)
    assert "TOP_SECRET_TOKEN" not in rendered
    assert "proxy-secret" not in rendered
    assert "-1001234567890" not in rendered


def test_diagnostic_network_error_does_not_expose_api_url(monkeypatch):
    from app.core.telegram import ptb_runtime

    monkeypatch.setattr(settings, "TELEGRAM_TOKEN", "configured-token", raising=False)
    monkeypatch.setattr(
        ptb_runtime,
        "get_send_bot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("401 https://api.telegram.org/bot123456:TOP_SECRET_TOKEN/getMe")
        ),
    )

    result = bot_diagnostics.TelegramBotDiagnostics._check_network()

    assert result["connection_test"] == "失败（RuntimeError）"
    assert "TOP_SECRET_TOKEN" not in repr(result)
    assert "api.telegram.org" not in repr(result)
