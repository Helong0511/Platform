"""Postback 标准化与校验边界回归测试。"""
from decimal import Decimal

import pytest

from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback.validators.data_validator import DataValidator


@pytest.mark.parametrize(
    "payload",
    [
        {"clk_id": "click-1", "amount": "1.2500"},
        {"cid": "click-2", "payout": "2.0000"},
        {"conversionId": "conversion-3", "amount": "3.5000"},
        {"clickId": "click-4", "payout": "4"},
    ],
)
def test_validator_accepts_all_click_id_and_payout_aliases(payload):
    valid, errors = DataValidator.validate(payload, "test-platform")
    assert valid is True
    assert errors == []


@pytest.mark.parametrize(
    "payout",
    ["NaN", "Infinity", "-Infinity", "0", "-1", "1.12345", "100000000", "not-a-number"],
)
def test_validator_rejects_non_finite_invalid_precision_and_out_of_range_payout(payout):
    valid, errors = DataValidator.validate(
        {"click_id": "click-1", "payout": payout},
        "test-platform",
    )
    assert valid is False
    assert any("payout" in error for error in errors)


def test_validator_rejects_overlong_event_name_before_database_write():
    valid, errors = DataValidator.validate(
        {
            "conversion_id": "conversion-1",
            "payout": "1.0000",
            "event_name": "x" * 101,
        },
        "test-platform",
    )
    assert valid is False
    assert "event_name 过长（最大 100 字符）" in errors


def test_normalizer_preserves_explicit_zero_payout_instead_of_falling_back_to_amount():
    normalized = DataNormalizer.normalize(
        {
            "click_id": "click-1",
            "payout": "0",
            "amount": "12.0000",
        },
        "test-platform",
    )
    assert normalized["payout"] == Decimal("0")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_normalizer_rejects_non_finite_decimal_values(value):
    assert DataNormalizer._parse_decimal(value) is None



def test_validator_checks_conversion_id_even_when_click_id_is_short():
    valid, errors = DataValidator.validate(
        {
            "click_id": "short-click",
            "conversion_id": "x" * 201,
            "payout": "1.0000",
        },
        "test-platform",
    )
    assert valid is False
    assert any("过长" in error for error in errors)
