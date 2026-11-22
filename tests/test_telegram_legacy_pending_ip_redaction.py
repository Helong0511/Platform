"""旧版 Telegram 待审批通知也必须掩码来源 IP。"""
from types import SimpleNamespace

from app.services.telegram_notification_service import TelegramNotificationService


def _build_message(ip):
    pending = SimpleNamespace(
        conversion_id="conv-safe-1",
        platform="bft",
        request_ip=ip,
        payout=1.25,
        original_payout=1.50,
        created_at=None,
        id=123,
    )
    return TelegramNotificationService.build_pending_conversion_message(pending)[0]


def test_legacy_pending_message_masks_ipv4():
    message = _build_message("203.0.113.42")

    assert "203.0.113.x" in message
    assert "203.0.113.42" not in message


def test_legacy_pending_message_masks_ipv6():
    message = _build_message("2001:db8:abcd:12:1111:2222:3333:4444")

    assert "2001:db8:abcd:12::/64" in message
    assert "1111:2222:3333:4444" not in message


def test_legacy_pending_message_never_echoes_invalid_ip():
    message = _build_message("untrusted-ip-secret")

    assert "[已隐藏]" in message
    assert "untrusted-ip-secret" not in message
