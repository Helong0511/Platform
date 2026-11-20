"""Postback Telegram 转发通知不得输出 URL、异常正文或原始参数。"""
from datetime import datetime
from types import SimpleNamespace

from app.services.telegram_notification_service import TelegramNotificationService


def _models():
    conversion = SimpleNamespace(
        conversion_id="conv-123",
        platform="partner",
        created_at=datetime(2026, 11, 20, 12, 0, 0),
    )
    publisher = SimpleNamespace(
        id=7,
        publisher_name="publisher",
        postback_url="https://partner.example/callback?token=private-token&email=user@example.com",
    )
    return conversion, publisher


def test_forward_failure_message_omits_secrets_and_click_params():
    conversion, publisher = _models()
    message = TelegramNotificationService.build_admin_forward_failure_message(
        conversion=conversion,
        publisher=publisher,
        error_message="HTTP error: https://internal.example/?password=private-password",
        click_params={
            "click_id": "private-click-id",
            "email": "user@example.com",
            "authorization": "Bearer private-token",
        },
    )

    # Telegram 消息必须使用真实换行符，而不是字面量反斜杠+n。
    assert "\n平台：" in message
    assert "\\n平台：" not in message
    for secret in (
        "partner.example",
        "private-token",
        "user@example.com",
        "private-password",
        "private-click-id",
        "authorization",
        "internal.example",
    ):
        assert secret not in message
    assert "受访问控制的转发日志" in message
    assert "publisher" in message


def test_forward_success_message_omits_target_url_and_response_body():
    conversion, publisher = _models()
    message = TelegramNotificationService.build_admin_forward_success_message(
        conversion=conversion,
        publisher=publisher,
        response_status=200,
        response_body='{"token":"private-token","email":"user@example.com"}',
    )

    assert "\n平台：" in message
    assert "\\n平台：" not in message
    assert "200" in message
    assert "partner.example" not in message
    assert "private-token" not in message
    assert "user@example.com" not in message
    assert "响应正文：已省略" in message
