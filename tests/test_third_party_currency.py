from decimal import Decimal

import pytest

from app.core.third_party_currency import (
    MAX_PURCHASE_AMOUNT,
    normalize_currency,
    validate_purchase_payload,
)


@pytest.mark.parametrize(
    ("amount", "currency", "expected_amount", "expected_currency"),
    [
        ("0.1", "usd", Decimal("0.1"), "USD"),
        ("0.1234", "CNY", Decimal("0.1234"), "CNY"),
        ("99999999.9999", "EUR", MAX_PURCHASE_AMOUNT, "EUR"),
    ],
)
def test_validate_purchase_payload_accepts_exact_decimal_and_normalizes_currency(
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
        ("1.00", None),
        ("1.00", ""),
        ("1.00", "US"),
        ("1.00", "USDD"),
    ],
)
def test_validate_purchase_payload_rejects_invalid_financial_values(amount, currency):
    with pytest.raises(ValueError):
        validate_purchase_payload(amount, currency)


def test_normalize_currency_does_not_invent_default():
    assert normalize_currency(None) is None
    assert normalize_currency("  ") is None
    assert normalize_currency(" cny ") == "CNY"
