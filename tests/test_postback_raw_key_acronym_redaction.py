"""Postback 原始数据脱敏：驼峰缩写字段名回归测试。"""
from app.core.postback.savers.conversion_saver import sanitize_postback_raw_data


def test_sensitive_acronym_keys_are_removed_from_nested_payloads():
    payload = {
        "clientIP": "203.0.113.10",
        "IPAddress": "203.0.113.11",
        "IDFAValue": "sensitive-idfa",
        "deviceID": "sensitive-device-id",
        "nested": {
            "userAgent": "sensitive-user-agent",
            "emailAddress": "person@example.invalid",
        },
        "safeField": "keep-me",
    }

    sanitized = sanitize_postback_raw_data(payload)

    assert "clientIP" not in sanitized
    assert "IPAddress" not in sanitized
    assert "IDFAValue" not in sanitized
    assert "deviceID" not in sanitized
    assert "userAgent" not in sanitized["nested"]
    assert "emailAddress" not in sanitized["nested"]
    assert sanitized["safeField"] == "keep-me"
    assert "203.0.113." not in repr(sanitized)
    assert "sensitive-" not in repr(sanitized)
    assert "person@example.invalid" not in repr(sanitized)
