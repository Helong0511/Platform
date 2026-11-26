from decimal import Decimal

import pytest

from app.core.third_party_currency import (
    DEFAULT_CURRENCY,
    MAX_PURCHASE_AMOUNT,
    normalize_currency,
    resolve_currency,
    validate_iso_currency,
    validate_purchase_payload,
)


@pytest.mark.parametrize(
    ("amount", "currency", "expected_amount", "expected_currency"),
    [
        ("0.1", "usd", Decimal("0.1"), "USD"),
        ("0.1234", "CNY", Decimal("0.1234"), "CNY"),
        ("99999999.9999", "EUR", MAX_PURCHASE_AMOUNT, "EUR"),
        ("1.00", None, Decimal("1.00"), "USD"),
        ("1.00", "  ", Decimal("1.00"), "USD"),
    ],
)
def test_validate_purchase_payload_accepts_iso_currency_and_usd_fallback(
    amount, currency, expected_amount, expected_currency
):
    actual_amount, actual_currency = validate_purchase_payload(amount, currency)
    assert actual_amount == expected_amount
    assert actual_currency == expected_currency


@pytest.mark.parametrize(
    ("amount", "currency"),
    [
        (None, "USD"),
        ("0", "USD"),
        ("-0.01", "USD"),
        ("NaN", "USD"),
        ("Infinity", "USD"),
        ("100000000", "USD"),
        ("1.00001", "USD"),
    ],
)
def test_validate_purchase_payload_rejects_invalid_financial_values(amount, currency):
    with pytest.raises(ValueError):
        validate_purchase_payload(amount, currency)


@pytest.mark.parametrize("currency", ["ZZZ", "US", "USDD", "XXX", "XTS", "XAU", "BOV", "CLF", "HRK", "VEF", ""])
def test_validate_iso_currency_rejects_non_settlement_or_invalid_codes(currency):
    with pytest.raises(ValueError):
        validate_iso_currency(currency)


@pytest.mark.parametrize("currency", ["USD", "CNY", "EUR", "JPY", "KWD"])
def test_validate_iso_currency_accepts_current_iso_4217_currencies(currency):
    assert validate_iso_currency(currency) == currency


def test_resolve_currency_records_fallback_attribution():
    assert resolve_currency(None) == (DEFAULT_CURRENCY, "system_fallback_usd")
    assert resolve_currency(" cny ", source="upstream_field:currency_code") == (
        "CNY",
        "upstream_field:currency_code",
    )


def test_normalize_currency_uses_usd_fallback():
    assert normalize_currency(None) == "USD"
    assert normalize_currency("  ") == "USD"
    assert normalize_currency(" cny ") == "CNY"
