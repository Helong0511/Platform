import json
from urllib.parse import quote

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
        "devad_id": "devad-value",
        "user_agent": "private-agent",
        "ua": "private-ua",
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
        "&x_user_token=compound-secret&devad_id=device-ad-secret"
        "&user_agent=private-agent&click_id=click-200"
    )

    result = sanitize_postback_raw_data(raw)

    assert "user@example.com" not in result
    assert "203.0.113.20" not in result
    assert "%2B1-555-0123" not in result
    assert "compound-secret" not in result
    assert "device-ad-secret" not in result
    assert "private-agent" not in result
    assert "click_id=click-200" in result
    assert "[redacted]" in result



def test_redacts_single_and_double_url_encoded_json_strings():
    payload = {
        "email": "encoded@example.com",
        "ip_address": "203.0.113.77",
        "nested": {"phoneNumber": "+1-555-0144"},
        "click_id": "keep-encoded-json-click",
        "event_name": "purchase",
    }
    raw_json = json.dumps(payload, separators=(",", ":"))
    single_encoded = quote(raw_json, safe="")
    double_encoded = quote(single_encoded, safe="")
    triple_encoded = quote(double_encoded, safe="")

    for raw in (single_encoded, double_encoded, triple_encoded):
        result = sanitize_postback_raw_data(raw)
        assert isinstance(result, str)
        decoded = json.loads(result)
        assert decoded["click_id"] == "keep-encoded-json-click"
        assert decoded["event_name"] == "purchase"
        assert "email" not in decoded
        assert "ip_address" not in decoded
        assert "phoneNumber" not in decoded["nested"]
        assert "encoded@example.com" not in result
        assert "203.0.113.77" not in result
        assert "+1-555-0144" not in result


def test_redacts_double_url_encoded_query_keys_and_values():
    raw_query = (
        "https://tracker.example/callback?%65mail=person%2540example.com"
        "&%2569p=203.0.113.88&click_id=keep-query-click"
    )
    raw = quote(quote(raw_query, safe=""), safe="")

    result = sanitize_postback_raw_data(raw)

    assert "person@example.com" not in result
    assert "203.0.113.88" not in result
    assert "email=" in result
    assert "ip=" in result
    assert "click_id=keep-query-click" in result
    assert "[redacted]" in result


def test_redacts_url_encoded_sensitive_dictionary_keys():
    result = sanitize_postback_raw_data({
        "%65mail": "encoded-key@example.com",
        "%2569p": "203.0.113.99",
        "click_id": "trusted-click",
        "event_name": "purchase",
    })

    assert result == {"click_id": "trusted-click", "event_name": "purchase"}
    serialized = json.dumps(result)
    assert "encoded-key@example.com" not in serialized
    assert "203.0.113.99" not in serialized


def test_preserves_non_sensitive_percent_encoded_business_values():
    original = "click%2Fid%2Dwith%252Fencoding"
    result = sanitize_postback_raw_data({"click_id": original})

    assert result["click_id"] == original



def test_redacts_url_encoded_json_nested_inside_outer_json_string():
    inner = json.dumps({
        "email": "nested-encoded@example.com",
        "click_id": "nested-click-preserved",
    }, separators=(",", ":"))
    outer = json.dumps({
        "payload": quote(inner, safe=""),
        "event_name": "purchase",
    }, separators=(",", ":"))

    result = sanitize_postback_raw_data(outer)
    decoded_outer = json.loads(result)
    decoded_inner = json.loads(decoded_outer["payload"])

    assert decoded_outer["event_name"] == "purchase"
    assert decoded_inner == {"click_id": "nested-click-preserved"}
    assert "nested-encoded@example.com" not in result


def test_large_json_string_is_omitted_instead_of_truncated():
    raw = json.dumps({"event_name": "x" * 5000})

    result = sanitize_postback_raw_data(raw)

    assert result == "[structured payload omitted: exceeds string limit]"



def test_redacts_percent_encoded_json_with_utf8_bom():
    raw_json = "\ufeff" + json.dumps({
        "email": "bom@example.com",
        "click_id": "bom-click-preserved",
    }, separators=(",", ":"))
    raw = quote(raw_json, safe="")

    result = sanitize_postback_raw_data(raw)
    decoded = json.loads(result)

    assert decoded == {"click_id": "bom-click-preserved"}
    assert "bom@example.com" not in result



def test_omits_payloads_that_remain_percent_encoded_after_decode_limit():
    payload = json.dumps({
        "email": "too-deep@example.com",
        "click_id": "keep-if-decodable",
    }, separators=(",", ":"))
    over_encoded = payload
    for _ in range(4):
        over_encoded = quote(over_encoded, safe="")

    result = sanitize_postback_raw_data(over_encoded)

    assert result == "[encoded raw payload omitted]"
    assert "too-deep@example.com" not in result


def test_drops_dictionary_keys_that_remain_percent_encoded_after_decode_limit():
    encoded_email_key = "email"
    for _ in range(4):
        encoded_email_key = quote(encoded_email_key, safe="")

    result = sanitize_postback_raw_data({
        encoded_email_key: "too-deep-key@example.com",
        "click_id": "trusted-click",
    })

    assert result == {"click_id": "trusted-click"}
    assert "too-deep-key@example.com" not in json.dumps(result)
