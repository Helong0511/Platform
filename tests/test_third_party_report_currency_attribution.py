"""第三方上报日志列表必须完整保留币种来源归因。"""
from datetime import datetime
from types import SimpleNamespace

from app.schemas.third_party_report import ThirdPartyReportLogListResponse


def _report_row(**overrides):
    values = {
        "id": 1,
        "source": "postback",
        "adsid": "masked-click-id",
        "event": "Purchase",
        "currency": "USD",
        "currency_source": "upstream_field:currency_code",
        "status": "success",
        "created_at": datetime(2026, 11, 28, 12, 0, 0),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_third_party_report_list_response_preserves_currency_source():
    payload = ThirdPartyReportLogListResponse.model_validate(_report_row()).model_dump()

    assert payload["currency"] == "USD"
    assert payload["currency_source"] == "upstream_field:currency_code"


def test_third_party_report_list_response_keeps_legacy_unknown_source():
    payload = ThirdPartyReportLogListResponse.model_validate(
        _report_row(currency="USD", currency_source="legacy_unknown")
    ).model_dump()

    assert payload["currency"] == "USD"
    assert payload["currency_source"] == "legacy_unknown"


def test_third_party_report_list_response_does_not_invent_missing_source():
    payload = ThirdPartyReportLogListResponse.model_validate(
        _report_row(currency_source=None)
    ).model_dump()

    assert payload["currency_source"] is None
