"""Telegram 待审批通知不得向群聊泄露完整来源 IP。"""
from app.core.telegram.notification_templates import (
    ConversionNotificationTemplate,
    _mask_ip_for_telegram,
)


def test_pending_approval_masks_ipv4_host_octet():
    message, _ = ConversionNotificationTemplate.format_pending_approval(
        platform="bft", conversion_id="conv-1", payout=1.25,
        ip="203.0.113.42", pending_id=10,
    )
    assert "203.0.113.x" in message
    assert "203.0.113.42" not in message


def test_pending_approval_masks_ipv6_to_network_prefix():
    message, _ = ConversionNotificationTemplate.format_pending_approval(
        platform="bft", conversion_id="conv-2", payout=2.5,
        ip="2001:db8:abcd:12:1111:2222:3333:4444", pending_id=11,
    )
    assert "2001:db8:abcd:12::/64" in message
    assert "1111:2222:3333:4444" not in message


def test_invalid_ip_is_not_echoed_into_telegram_message():
    message, _ = ConversionNotificationTemplate.format_pending_approval(
        platform="bft", conversion_id="conv-3", payout=3.0,
        ip="untrusted-input-secret", pending_id=12,
    )
    assert "[已隐藏]" in message
    assert "untrusted-input-secret" not in message


def test_pending_approval_escapes_untrusted_html_fields():
    message, _ = ConversionNotificationTemplate.format_pending_approval(
        platform="<b>evil</b>", conversion_id="<script>value</script>",
        payout=1.0, ip="192.0.2.8", pending_id=13,
    )
    assert "<b>evil</b>" not in message
    assert "&lt;b&gt;evil&lt;/b&gt;" in message
    assert "&lt;script&gt;value&lt;/script&gt;" in message


def test_invalid_ip_mask_helper_never_returns_input():
    assert _mask_ip_for_telegram("not-an-ip") == "[已隐藏]"
