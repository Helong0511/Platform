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
