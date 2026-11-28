"""Offer 统计的多币种金额隔离与 Decimal 精度回归测试。"""
from decimal import Decimal

from app.services.cpl.offer_stats import (
    serialize_currency_revenue_groups,
    single_group_revenue_trend,
    single_trusted_revenue_amount,
)


def test_revenue_groups_keep_currency_and_source_separate():
    groups = serialize_currency_revenue_groups([
        ("USD", "offer_config", Decimal("10.250000")),
        ("EUR", "offer_config", Decimal("8.500000")),
        ("USD", "system_fallback_usd", Decimal("2.000000")),
    ])

    assert groups == [
        {"currency": "EUR", "currency_source": "offer_config", "amount": "8.500000"},
        {"currency": "USD", "currency_source": "offer_config", "amount": "10.250000"},
        {"currency": "USD", "currency_source": "system_fallback_usd", "amount": "2.000000"},
    ]
    assert single_trusted_revenue_amount(groups) is None


def test_legacy_unknown_amount_is_never_reported_as_usd():
    groups = serialize_currency_revenue_groups([
        (None, None, Decimal("123.456789")),
    ])

    assert groups == [{
        "currency": "LEGACY_UNKNOWN",
        "currency_source": "legacy_unknown",
        "amount": "123.456789",
    }]
    assert single_trusted_revenue_amount(groups) is None
    assert single_group_revenue_trend(groups, groups) is None


def test_single_trusted_currency_keeps_exact_decimal_amount():
    groups = serialize_currency_revenue_groups([
        ("KWD", "offer_config", Decimal("12.345000")),
    ])

    assert single_trusted_revenue_amount(groups) == "12.345000"


def test_revenue_trend_requires_same_currency_and_source_in_both_periods():
    current = serialize_currency_revenue_groups([
        ("USD", "offer_config", Decimal("110.000000")),
    ])
    previous = serialize_currency_revenue_groups([
        ("USD", "offer_config", Decimal("100.000000")),
    ])

    assert single_group_revenue_trend(current, previous) == 10.0


def test_revenue_trend_is_unavailable_when_previous_group_is_missing():
    current = serialize_currency_revenue_groups([
        ("EUR", "offer_config", Decimal("110.00")),
    ])
    previous = serialize_currency_revenue_groups([
        ("USD", "offer_config", Decimal("100.00")),
    ])

    assert single_group_revenue_trend(current, previous) is None


def test_revenue_trend_does_not_cross_currency_source_attribution():
    current = serialize_currency_revenue_groups([
        ("USD", "offer_config", Decimal("110.00")),
    ])
    previous = serialize_currency_revenue_groups([
        ("USD", "system_fallback_usd", Decimal("100.00")),
    ])

    assert single_group_revenue_trend(current, previous) is None
