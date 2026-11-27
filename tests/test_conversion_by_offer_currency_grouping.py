"""按 Offer 汇总时验证历史转化币种归因与 Decimal 精度。"""
from decimal import Decimal

from app.services.cpl.conversion_service import _build_offer_currency_breakdown


def test_offer_summary_keeps_currency_and_source_groups_separate():
    result = _build_offer_currency_breakdown([
        ("USD", "offer_config", 2, Decimal("10.250000")),
        ("EUR", "offer_config", 1, Decimal("8.500000")),
        ("USD", "system_fallback_usd", 1, Decimal("2.000000")),
    ])

    assert result["count"] == 4
    assert result["po"] is None
    assert result["currency"] is None
    assert result["currency_groups"] == [
        {
            "currency": "EUR",
            "currency_source": "offer_config",
            "amount": "8.500000",
            "conversion_count": 1,
        },
        {
            "currency": "USD",
            "currency_source": "offer_config",
            "amount": "10.250000",
            "conversion_count": 2,
        },
        {
            "currency": "USD",
            "currency_source": "system_fallback_usd",
            "amount": "2.000000",
            "conversion_count": 1,
        },
    ]


def test_offer_summary_never_relabels_unknown_history_as_usd():
    result = _build_offer_currency_breakdown([
        (None, None, 3, Decimal("123.456789")),
    ])

    assert result["count"] == 3
    assert result["po"] is None
    assert result["currency"] is None
    assert result["currency_groups"] == [
        {
            "currency": "LEGACY_UNKNOWN",
            "currency_source": "legacy_unknown",
            "amount": "123.456789",
            "conversion_count": 3,
        }
    ]


def test_offer_summary_legacy_amount_fields_only_exist_for_one_trusted_group():
    result = _build_offer_currency_breakdown([
        ("KWD", "offer_config", 2, Decimal("12.345000")),
    ])

    assert result["count"] == 2
    assert result["po"] == "12.345000"
    assert result["currency"] == "KWD"
