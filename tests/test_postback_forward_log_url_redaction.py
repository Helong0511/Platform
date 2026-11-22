"""Postback 转发日志 API 不得泄露下游 URL 中的认证信息。"""

import pytest

from app.services.cpl.postback_forward_log_service import _safe_downstream_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "https://api-user:secret-token@downstream.example:8443/callback"
            "?click_id=private-click&email=buyer@example.invalid#fragment",
            "https://downstream.example:8443",
        ),
        (
            "HTTP://user:password@[2001:db8::1]:8080/path?token=secret",
            "http://[2001:db8::1]:8080",
        ),
        ("https://downstream.example/callback?api_key=secret", "https://downstream.example"),
        ("https://downstream.example:invalid/callback", "历史下游 URL 已脱敏"),
        ("not a valid URL", "历史下游 URL 已脱敏"),
        ("", "历史下游 URL 已脱敏"),
        (None, "历史下游 URL 已脱敏"),
    ],
)
def test_safe_downstream_url_never_returns_userinfo_or_request_data(value, expected):
    assert _safe_downstream_url(value) == expected
