from decimal import Decimal

import pytest

from app.api_v1.tb_search_data import _parse_decimal_cell


def test_parse_decimal_cell_preserves_decimal_text_precision():
    assert _parse_decimal_cell("123456789.123456", "REVENUE") == Decimal("123456789.123456")


def test_parse_decimal_cell_converts_float_via_shortest_decimal_text():
    # pandas 读取 Excel 数值后可能提供 float；str() 避免直接导入其二进制展开值。
    assert _parse_decimal_cell(0.1, "REVENUE") == Decimal("0.1")


def test_parse_decimal_cell_uses_default_for_blank_values():
    assert _parse_decimal_cell(None, "REVENUE") == Decimal("0")
    assert _parse_decimal_cell("", "REVENUE", Decimal("0.00")) == Decimal("0.00")


@pytest.mark.parametrize("value", ["not-a-number", "NaN", "Infinity", "-Infinity"])
def test_parse_decimal_cell_rejects_invalid_or_non_finite_values(value):
    with pytest.raises(ValueError):
        _parse_decimal_cell(value, "REVENUE")


def test_apply_deduct_ratio_can_preserve_fractional_precision():
    from app.core.utils import apply_deduct_ratio

    assert apply_deduct_ratio(
        Decimal("1.239"), Decimal("0.1"), truncate_places=None
    ) == Decimal("1.1151")


def test_apply_deduct_ratio_keeps_legacy_two_decimal_default():
    from app.core.utils import apply_deduct_ratio

    assert apply_deduct_ratio(
        Decimal("1.239"), Decimal("0.1")
    ) == Decimal("1.11")
