"""旧 Telegram 通知模板不得暴露异常正文，并须转义 HTML 字段。"""
from app.core.telegram.notification_templates import (
    ConversionNotificationTemplate,
    SystemNotificationTemplate,
)


def test_conversion_template_escapes_untrusted_html_fields():
    message = ConversionNotificationTemplate.format_conversion(
        platform="<b>evil</b>",
        conversion_id="<script>secret</script>",
        event_name="<i>event</i>",
        payout=1.25,
        product_name="<a href='x'>product</a>",
        advertiser_name="<img src=x>",
        publisher_name="<code>publisher</code>",
    )

    assert "<b>evil</b>" not in message
    assert "&lt;b&gt;evil&lt;/b&gt;" in message
    assert "<script>" not in message
    assert "&lt;script&gt;" in message
    assert "<a href=" not in message
    assert "&lt;a href=" in message


def test_forward_failure_template_omits_exception_payload():
    secret = "token=private-password https://api.example/postback?api_key=TOPSECRET"
    message = SystemNotificationTemplate.format_forward_failure(
        platform="test-platform",
        conversion_id="conv-1",
        publisher_name="publisher",
        error_message=secret,
    )

    assert "test-platform" in message
    assert "private-password" not in message
    assert "TOPSECRET" not in message
    assert "api.example" not in message
    assert "受访问控制的转发日志" in message


def test_system_error_template_omits_message_and_context():
    secret = "postgres://user:private-password@db/private?token=TOPSECRET"
    message = SystemNotificationTemplate.format_system_error(
        error_type=secret,
        error_message=secret,
        context={"connection": secret, "absolute_path": "/srv/app/.env"},
    )

    assert "系统错误" in message
    assert "private-password" not in message
    assert "TOPSECRET" not in message
    assert "postgres://" not in message
    assert "/srv/app" not in message
