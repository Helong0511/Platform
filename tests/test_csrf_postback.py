"""CSRF Postback 豁免路径单元测试。"""
from app.core.csrf import _is_external_postback_callback


def test_external_platform_callback_exempt():
    assert _is_external_postback_callback("/api/v1/bft/postback") is True
    assert _is_external_postback_callback("/api/v1/postback/appsflyer") is True


def test_admin_postback_routes_not_exempt():
    assert _is_external_postback_callback("/api/v1/postback/conversions") is False
    assert _is_external_postback_callback("/api/v1/postback/stats") is False
    assert _is_external_postback_callback("/api/v1/postback/check-duplicates") is False
