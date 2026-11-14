"""第三方上报管理 API 的个人信息脱敏测试。"""
import json

from app.api_v1.system.third_party_reports import (
    _mask_report_pii,
    _mask_report_ad_identifier,
    _sanitize_report_params,
    _safe_report_error_message,
    _can_requeue_report,
    _is_outbox_processing,
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
        assert "pii_scrubbed_at" in response_schema.model_fields
        assert "manual_retry_count" in response_schema.model_fields

    assert "outbox_error_category" in ThirdPartyReportLogListResponse.model_fields
    assert "can_requeue" in ThirdPartyReportLogListResponse.model_fields
    assert "report_params_preview" in ThirdPartyReportLogListResponse.model_fields
    assert "outbox_payload_editable" in ThirdPartyReportLogListResponse.model_fields
    assert "outbox_processing" in ThirdPartyReportLogListResponse.model_fields
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



def test_manual_requeue_eligibility_matches_backend_guards():
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    from app.core.third_party_report import REPORT_LOG_LEASE_SECONDS

    now = datetime(2026, 11, 11, 12, 0, 0)
    base = {
        "outbox_enqueued": True,
        "identity_scope": "platform_scoped",
        "platform": "meta",
        "pii_scrubbed_at": None,
        "status": "failed",
        "short_link_id": 17,
        "cloak_name": None,
        "short_code": None,
        "report_start_time": None,
    }

    assert _can_requeue_report(SimpleNamespace(**base), now) is True
    assert _can_requeue_report(
        SimpleNamespace(**{**base, "manual_retry_count": 3}), now
    ) is False
    assert _can_requeue_report(
        SimpleNamespace(**{**base, "outbox_enqueued": False}), now
    ) is False
    assert _can_requeue_report(
        SimpleNamespace(**{**base, "status": "pending"}), now
    ) is False
    assert _can_requeue_report(
        SimpleNamespace(**{**base, "short_link_id": None}), now
    ) is False
    assert _can_requeue_report(
        SimpleNamespace(**{**base, "pii_scrubbed_at": now}), now
    ) is False
    assert _can_requeue_report(
        SimpleNamespace(**{
            **base,
            "report_start_time": now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS),
        }),
        now,
    ) is False
    assert _can_requeue_report(
        SimpleNamespace(**{
            **base,
            "report_start_time": now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 2),
        }),
        now,
    ) is True
    assert _can_requeue_report(
        SimpleNamespace(**{
            **base,
            "error_message": "短链接已删除，无法解析像素配置",
        }),
        now,
    ) is False



def test_outbox_processing_state_uses_the_backend_lease_duration():
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    from app.core.third_party_report import REPORT_LOG_LEASE_SECONDS

    now = datetime(2026, 11, 11, 12, 0, 0)
    base = {
        "outbox_enqueued": True,
        "status": "failed",
        "report_start_time": now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS - 1),
    }
    assert _is_outbox_processing(SimpleNamespace(**base), now) is True
    assert _is_outbox_processing(
        SimpleNamespace(**{
            **base,
            "report_start_time": now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
        }),
        now,
    ) is False
    assert _is_outbox_processing(
        SimpleNamespace(**{**base, "outbox_enqueued": False}), now
    ) is False


def test_ad_click_identifier_is_partially_masked_in_admin_responses():
    """fbclid/click_id 属于可关联用户的在线标识，管理端不返回完整原值。"""
    assert _mask_report_ad_identifier("fbclid-1234567890") == "fbcl…7890"
    assert _mask_report_ad_identifier("12345678") == "[已隐藏]"
    assert _mask_report_ad_identifier("123456789") == "1234…6789"
    assert _mask_report_ad_identifier("") == ""
    assert _mask_report_ad_identifier(None) is None


def test_report_list_and_detail_mask_adsid_before_returning():
    from pathlib import Path
    source = Path("app/api_v1/system/third_party_reports.py").read_text(encoding="utf-8")
    assert 'item["adsid"] = _mask_report_ad_identifier(item.get("adsid"))' in source
    assert 'safe_data["adsid"] = _mask_report_ad_identifier(safe_data.get("adsid"))' in source


def test_report_api_errors_never_echo_raw_exception_details():
    """DB/driver 异常可能携带 SQL 参数或 PII，API 错误响应只返回固定文案。"""
    from pathlib import Path
    source = Path("app/api_v1/system/third_party_reports.py").read_text(encoding="utf-8")
    assert "str(e)" not in source
    assert "detail=f" not in source
