"""转化总览必须按币种分别汇总，不能跨币种求和。"""
from app.services.cpl.conversion_service import (
    _build_currency_summaries,
    _sanitize_conversion_summary_for_client,
)


def test_conversion_summary_groups_by_currency_and_source_with_decimal_precision():
    from decimal import Decimal

    summaries = _build_currency_summaries(
        [
            {
                "currency": "USD",
                "currency_source": "offer_config",
                "conversion_count": 2,
                "po": Decimal("10.125"),
                "po_after_discount": Decimal("8.500"),
            },
            {
                "currency": "USD",
                "currency_source": "manual_config",
                "conversion_count": 1,
                "po": Decimal("2.345"),
                "po_after_discount": Decimal("1.234"),
            },
            {
                "currency": "KWD",
                "currency_source": "postback_explicit",
                "conversion_count": 1,
                "po": Decimal("20.123"),
                "po_after_discount": Decimal("15.001"),
            },
            {
                "currency": "JPY",
                "currency_source": "postback_explicit",
                "conversion_count": 0,
                "po": Decimal("0"),
                "po_after_discount": Decimal("0"),
            },
        ]
    )
    assert [(item["currency"], item["currency_source"]) for item in summaries] == [
        ("KWD", "postback_explicit"),
        ("USD", "manual_config"),
        ("USD", "offer_config"),
    ]
    assert summaries[0]["total_po"] == "20.123"
    assert summaries[0]["total_profit"] == "5.122"
    assert summaries[1]["total_po"] == "2.345"
    assert summaries[2]["total_profit"] == "1.625"


def test_conversion_summary_does_not_assume_missing_currency_is_usd():
    summaries = _build_currency_summaries(
        [
            {
                "conversion_count": 1,
                "po": "12.345",
                "po_after_discount": "10.001",
            }
        ]
    )
    assert summaries[0]["currency"] == "LEGACY_UNKNOWN"
    assert summaries[0]["currency_source"] == "legacy_unknown"
    assert summaries[0]["total_po"] == "12.345"


def test_conversion_summary_skips_untrusted_or_incomplete_amount_rows():
    summaries = _build_currency_summaries(
        [
            {
                "currency": "USD",
                "currency_source": "legacy_unknown",
                "conversion_count": 1,
                "po": None,
                "po_after_discount": None,
            }
        ]
    )
    assert summaries == []


def test_client_conversion_summary_hides_upstream_and_profit_totals_per_currency():
    summary = _sanitize_conversion_summary_for_client(
        {
            "total_po": None,
            "total_po_after_discount": None,
            "total_profit": None,
            "currency_summaries": [
                {
                    "currency": "EUR",
                    "total_po": 20.0,
                    "total_po_after_discount": 15.0,
                    "total_profit": 5.0,
                }
            ],
            "stats_list": [
                {
                    "currency": "EUR",
                    "po": 20.0,
                    "po_after_discount": 15.0,
                    "adv_po": 20.0,
                    "publisher_name": "publisher",
                }
            ],
        }
    )
    assert "total_po" not in summary
    assert "total_profit" not in summary
    assert summary["currency_summaries"] == [
        {"currency": "EUR", "total_po_after_discount": 15.0}
    ]
    assert summary["stats_list"] == [
        {"currency": "EUR", "po_after_discount": 15.0, "publisher_name": "publisher"}
    ]
