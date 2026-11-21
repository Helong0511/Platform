import json

from app.core.postback.savers.conversion_saver import sanitize_postback_raw_data


def test_redacts_sensitive_fields_recursively_and_preserves_business_fields():
    payload = {
        "click_id": "clk-123",
        "conversion_id": "conv-456",
        "payout": "1.25",
        "email": "person@example.com",
        "phone_number": "+1-555-0100",
        "authorization": "Bearer secret",
        "access_token": "secret-token",
        "nested": {
            "session_id": "session-secret",
            "user_email": "nested@example.com",
            "event_name": "purchase",
            "metadata": [{"api_key": "secret", "currency": "USD"}],
        },
    }

    result = sanitize_postback_raw_data(payload)

    assert result["click_id"] == "clk-123"
    assert result["conversion_id"] == "conv-456"
    assert result["payout"] == "1.25"
    assert result["nested"]["event_name"] == "purchase"
    assert result["nested"]["metadata"] == [{"currency": "USD"}]
    serialized = json.dumps(result)
    for secret in (
        "person@example.com",
        "+1-555-0100",
        "Bearer secret",
        "secret-token",
        "session-secret",
        "nested@example.com",
        '"api_key"',
    ):
        assert secret not in serialized


def test_redacts_ip_and_device_identifiers_from_raw_snapshot():
    result = sanitize_postback_raw_data({
        "ip": "203.0.113.10",
        "ip_address": "203.0.113.11",
        "idfa": "idfa-value",
        "gaid": "gaid-value",
        "advertising_id": "ad-id",
        "device_id": "device-id",
        "click_id": "click-1",
    })

    assert result == {"click_id": "click-1"}


def test_limits_nested_depth_and_item_count():
    deep = {"level": {"level": {"level": {"level": {"level": {"level": {"level": {"level": {"level": "secret"}}}}}}}}}
    result = sanitize_postback_raw_data(deep)
    assert "[omitted]" in json.dumps(result)


def test_oversized_payload_is_replaced_with_size_marker():
    result = sanitize_postback_raw_data({"event": "x" * 40000})
    assert result[" _redaction".strip()] == "payload_exceeds_storage_limit"
    assert result["_sanitized_size_bytes"] > 32 * 1024


def test_unknown_objects_are_not_serialized_with_repr():
    class SecretObject:
        def __repr__(self):
            return "password=do-not-leak"

    result = sanitize_postback_raw_data({"metadata": SecretObject()})
    assert result == {"metadata": "[unsupported value omitted]"}
    assert "do-not-leak" not in json.dumps(result)
