"""第三方上报管理 API 的个人信息脱敏测试。"""
import json

from app.api_v1.system.third_party_reports import (
    _mask_report_pii,
    _sanitize_report_params,
)


def test_mask_report_pii_fields():
    assert _mask_report_pii("alice@example.invalid", "email") == "a***@example.invalid"
    assert _mask_report_pii("+1 (415) 555-0123", "phone") == "141****0123"
    assert _mask_report_pii("203.0.113.73", "ip") == "203.0.*.*"
    assert _mask_report_pii("Mozilla/5.0 test agent", "ua") == "[已隐藏]"
    assert _mask_report_pii(None, "email") is None


def test_sanitize_report_params_recursively():
    raw = json.dumps(
        {
            "user": {
                "email": "alice@example.invalid",
                "phone": "4155550123",
                "ip": "203.0.113.73",
                "ua": "private-agent",
            },
            "event": "Purchase",
            "items": [{"email": "bob@example.invalid"}],
            "data": [{
                "user_data": {
                    "em": ["alice@example.invalid"],
                    "ph": ["4155550123"],
                    "client_ip_address": "198.51.100.7",
                    "client_user_agent": "private-meta-agent",
                    "external_id": "customer-unique-identifier",
                }
            }],
        }
    )

    sanitized = json.loads(_sanitize_report_params(raw))

    assert sanitized["user"]["email"] == "a***@example.invalid"
    assert sanitized["user"]["phone"] == "415****0123"
    assert sanitized["user"]["ip"] == "203.0.*.*"
    assert sanitized["user"]["ua"] == "[已隐藏]"
    assert sanitized["items"][0]["email"] == "b***@example.invalid"
    assert sanitized["data"][0]["user_data"]["em"] == ["a***@example.invalid"]
    assert sanitized["data"][0]["user_data"]["ph"] == ["415****0123"]
    assert sanitized["data"][0]["user_data"]["client_ip_address"] == "198.51.*.*"
    assert sanitized["data"][0]["user_data"]["client_user_agent"] == "[已隐藏]"
    assert sanitized["data"][0]["user_data"]["external_id"] == "[已隐藏]"
    assert sanitized["event"] == "Purchase"


def test_invalid_report_params_are_not_returned_raw():
    assert _sanitize_report_params("email=alice@example.invalid") == "[参数内容不可解析，已隐藏]"
    assert _sanitize_report_params(None) is None
