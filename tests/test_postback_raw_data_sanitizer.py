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
        "authToken": "camel-secret",
        "emailAddress": "camel@example.com",
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
        "camel-secret",
        "camel@example.com",
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
    # 单字段会先受 4 KiB 上限约束；用多个合法字段验证整体 JSON 体积上限。
    payload = {f"event_{index}": "x" * 4000 for index in range(10)}
    result = sanitize_postback_raw_data(payload)
    assert result["_redaction"] == "payload_exceeds_storage_limit"
    assert result["_sanitized_size_bytes"] > 32 * 1024


def test_unknown_objects_are_not_serialized_with_repr():
    class SecretObject:
        def __repr__(self):
            return "password=do-not-leak"

    result = sanitize_postback_raw_data({"metadata": SecretObject()})
    assert result == {"metadata": "[unsupported value omitted]"}
    assert "do-not-leak" not in json.dumps(result)


def test_redacts_sensitive_fields_inside_json_encoded_raw_string():
    raw = json.dumps({
        "email": "string@example.com",
        "access_token": "string-token-secret",
        "nested": {"phoneNumber": "+1-555-0199"},
        "click_id": "trusted-click-99",
        "event_name": "purchase",
    })

    result = sanitize_postback_raw_data(raw)

    assert isinstance(result, str)
    decoded = json.loads(result)
    assert decoded["click_id"] == "trusted-click-99"
    assert decoded["event_name"] == "purchase"
    assert "email" not in decoded
    assert "access_token" not in decoded
    assert "phoneNumber" not in decoded["nested"]
    assert "string@example.com" not in result
    assert "string-token-secret" not in result
    assert "+1-555-0199" not in result


def test_redacts_sensitive_query_parameters_and_authorization_headers():
    raw = (
        "https://tracker.example/callback?email=query@example.com"
        "&token=query-secret&click_id=click-100&ip=203.0.113.9\n"
        "Authorization: Bearer header-secret-token"
    )

    result = sanitize_postback_raw_data(raw)

    assert "query@example.com" not in result
    assert "query-secret" not in result
    assert "203.0.113.9" not in result
    assert "header-secret-token" not in result
    assert "click_id=click-100" in result
    assert "[redacted]" in result


def test_oversized_raw_string_is_omitted_without_persisting_prefix():
    raw = '{"email":"oversized@example.com","payload":"' + ("x" * 40000) + '"}'
    result = sanitize_postback_raw_data(raw)

    assert result == "[oversized raw string omitted]"
    assert "oversized@example.com" not in result



def test_redacts_composite_sensitive_query_and_form_parameter_names():
    raw = (
        "https://tracker.example/callback?user_email=user@example.com"
        "&client_ip=203.0.113.20&phone_number=%2B1-555-0123"
        "&x_user_token=compound-secret&click_id=click-200"
    )

    result = sanitize_postback_raw_data(raw)

    assert "user@example.com" not in result
    assert "203.0.113.20" not in result
    assert "%2B1-555-0123" not in result
    assert "compound-secret" not in result
    assert "click_id=click-200" in result
    assert "[redacted]" in result
