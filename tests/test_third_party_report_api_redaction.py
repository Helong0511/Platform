"""第三方上报管理 API 的个人信息脱敏测试。"""
import json

from app.api_v1.system.third_party_reports import (
    _mask_report_pii,
    _sanitize_report_params,
    _safe_report_error_message,
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



def test_third_party_report_response_schemas_expose_outbox_state():
    from app.schemas.third_party_report import (
        ThirdPartyReportLogListResponse,
        ThirdPartyReportLogResponse,
    )

    for response_schema in (ThirdPartyReportLogResponse, ThirdPartyReportLogListResponse):
        assert "outbox_enqueued" in response_schema.model_fields
        assert "next_retry_time" in response_schema.model_fields

    assert "outbox_error_category" in ThirdPartyReportLogListResponse.model_fields
    assert "can_requeue" in ThirdPartyReportLogListResponse.model_fields
    assert "error_message" in ThirdPartyReportLogResponse.model_fields
    assert "response_body" not in ThirdPartyReportLogResponse.model_fields



def test_report_error_message_is_classified_without_echoing_raw_details():
    raw_ip = "198.51.100.77"
    raw = f"尝试 1: 状态码: 400, 响应: email=alice@example.invalid ip={raw_ip}"
    safe = _safe_report_error_message(raw)
    assert safe == "第三方返回非成功状态"
    assert "alice@example.invalid" not in safe
    assert raw_ip not in safe
    assert _safe_report_error_message("像素凭据暂不可用，Outbox 将自动重试") == (
        "像素配置缺失或不可用；检查配置后可重新排队"
    )
