"""短链接重定向日志不得泄露请求参数或跳转地址。"""
import logging

from app.routes.short_link.handlers import log_redirect_details


def test_redirect_summary_does_not_log_sensitive_urls_or_parameters(caplog):
    sensitive_values = (
        "https://landing.example/path?access_token=secret-token",
        "https://advertiser.example/callback?api_key=secret-api-key",
        "fbclid=private-click-id",
        "secret-click-id",
    )

    with caplog.at_level(logging.DEBUG, logger="app.routes.short_link.handlers"):
        log_redirect_details(
            short_code="abc123",
            click_id="secret-click-id",
            final_offer_id=12,
            final_channel_id=34,
            advertiser_id=56,
            request_params={"access_token": "secret-token", "fbclid": "private-click-id"},
            original_url_before_replace=sensitive_values[0],
            original_url_after_replace=sensitive_values[1],
            final_url=sensitive_values[1],
            request=None,
        )

    output = caplog.text
    for secret in sensitive_values:
        assert secret not in output
    assert "abc123" in output
    assert "offer_id=12" in output
    assert "channel_id=34" in output
