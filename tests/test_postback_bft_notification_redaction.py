"""BFT Telegram 通知不得转发原始敏感回调参数。"""
import pytest

from app.services.cpl.postback_bft_service import _format_bft_notification_value


@pytest.mark.parametrize(
    "key",
    [
        "access_token",
        "api_key",
        "authorization",
        "email",
        "phone",
        "client_ip",
        "request_ip",
        "click_id",
        "clk_id",
        "fbclid",
        "gclid",
        "conversion_id",
    ],
)
def test_sensitive_bft_fields_are_redacted(key):
    assert _format_bft_notification_value(key, "sensitive-value-123") == "[已脱敏]"


def test_unknown_bft_fields_are_omitted():
    assert (
        _format_bft_notification_value("custom_payload", "arbitrary-secret")
        == "[非白名单字段已省略]"
    )


def test_structured_bft_values_are_not_dumped():
    assert (
        _format_bft_notification_value("event", {"email": "person@example.com"})
        == "[结构化内容已省略]"
    )


def test_safe_bft_business_fields_remain_available():
    assert _format_bft_notification_value("event_name", "install") == "install"
    assert _format_bft_notification_value("payout", 1.25) == "1.25"


@pytest.mark.asyncio
async def test_bft_fire_and_forget_telegram_failure_is_logged(monkeypatch, caplog):
    import asyncio
    import logging
    from types import SimpleNamespace

    from app.services.cpl import postback_bft_service as bft_module
    from app.core.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_ADMIN", "123456789", raising=False)

    async def _failed_send(*_args, **_kwargs):
        return False

    monkeypatch.setattr(bft_module, "send_telegram_message_async", _failed_send)

    with caplog.at_level(logging.WARNING, logger="app.services.cpl.postback_bft_service"):
        await bft_module.postback_bft_service._notify_telegram(
            SimpleNamespace(method="POST"),
            {"event_name": "install"},
        )
        # 让 fire-and-forget 任务和 done callback 完成。
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert "BFT Postback Telegram 通知发送失败" in caplog.text
