"""转化总览必须按币种分别汇总，不能跨币种求和。"""
from app.services.cpl.conversion_service import (
    _build_currency_summaries,
    _sanitize_conversion_summary_for_client,
)


def test_conversion_summary_groups_revenue_by_currency_and_excludes_click_only_rows():
    summaries = _build_currency_summaries(
        [
            {
                "currency": "USD",
                "conversion_count": 2,
                "po": 10.125,
                "po_after_discount": 8.5,
            },
            {
                "currency": "EUR",
                "conversion_count": 1,
                "po": 20.0,
                "po_after_discount": 15.0,
            },
            {
                "currency": "JPY",
                "conversion_count": 0,
                "po": 0.0,
                "po_after_discount": 0.0,
            },
        ]
    )
    assert [item["currency"] for item in summaries] == ["EUR", "USD"]
    assert summaries[0]["total_po"] == 20.0
    assert summaries[1]["total_po"] == 10.125
    assert summaries[1]["total_profit"] == 1.625


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
