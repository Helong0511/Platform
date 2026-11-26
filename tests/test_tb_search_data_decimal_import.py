from decimal import Decimal

import pytest

from app.api_v1.tb_search_data import (
    _is_blank_excel_cell,
    _parse_decimal_cell,
    _parse_nonnegative_integer_cell,
)


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


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_parse_decimal_cell_rejects_non_finite_decimal_instances(value):
    with pytest.raises(ValueError):
        _parse_decimal_cell(value, "REVENUE")



def test_decimal_nan_is_not_treated_as_an_empty_rpm_cell():
    assert _is_blank_excel_cell(Decimal("NaN")) is False
    with pytest.raises(ValueError, match="有限数字"):
        _parse_decimal_cell(Decimal("NaN"), "RPM")


def test_decimal_infinity_is_not_treated_as_an_empty_rpm_cell():
    assert _is_blank_excel_cell(Decimal("Infinity")) is False
    with pytest.raises(ValueError, match="有限数字"):
        _parse_decimal_cell(Decimal("Infinity"), "RPM")


def test_pandas_nan_is_treated_as_an_empty_excel_cell():
    assert _is_blank_excel_cell(float("nan")) is True



@pytest.mark.parametrize(
    "field_name",
    ["revenue", "rpm", "revenue_before_deduct", "rpm_before_deduct"],
)
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_tb_search_schema_rejects_non_finite_manual_amounts(field_name, value):
    from app.schemas.tb_search_data import TBSearchDataUpdate

    with pytest.raises(ValueError, match="有限数字"):
        TBSearchDataUpdate(**{field_name: value})


def test_tb_search_schema_accepts_finite_decimal_manual_amounts():
    from app.schemas.tb_search_data import TBSearchDataUpdate

    update = TBSearchDataUpdate(revenue="123.456789", rpm="0.123456")
    assert update.revenue == Decimal("123.456789")
    assert update.rpm == Decimal("0.123456")



@pytest.mark.parametrize("value", [None, "", float("nan"), ""])
def test_counter_parser_defaults_blank_cells_to_zero(value):
    assert _parse_nonnegative_integer_cell(value, "CLICKS") == 0


@pytest.mark.parametrize("value, expected", [(0, 0), (12, 12), (12.0, 12), ("0012", 12), ("12.000", 12)])
def test_counter_parser_accepts_integral_nonnegative_values(value, expected):
    assert _parse_nonnegative_integer_cell(value, "CLICKS") == expected


@pytest.mark.parametrize(
    "value",
    ["1.5", -1, "-0.1", "NaN", "Infinity", "-Infinity", "not-a-number", "2147483648"],
)
def test_counter_parser_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="非负整数|数据库整数范围"):
        _parse_nonnegative_integer_cell(value, "CLICKS")



@pytest.mark.parametrize("field_name", ["redirects", "searches", "monetized", "clicks"])
@pytest.mark.parametrize("value", [-1, 2147483648])
def test_tb_search_manual_update_rejects_out_of_range_counters(field_name, value):
    from app.schemas.tb_search_data import TBSearchDataUpdate

    with pytest.raises(ValueError):
        TBSearchDataUpdate(**{field_name: value})


def test_tb_search_manual_update_accepts_zero_and_maximum_counter():
    from app.schemas.tb_search_data import TBSearchDataUpdate

    update = TBSearchDataUpdate(redirects=0, clicks=2147483647)
    assert update.redirects == 0
    assert update.clicks == 2147483647


@pytest.mark.parametrize(
    "field_name",
    [
        "product_id",
        "country_code",
        "redirects",
        "searches",
        "monetized",
        "clicks",
        "revenue",
        "rpm",
        "revenue_before_deduct",
        "rpm_before_deduct",
    ],
)
def test_tb_search_manual_update_rejects_explicit_null_for_non_nullable_fields(field_name):
    from app.schemas.tb_search_data import TBSearchDataUpdate

    with pytest.raises(ValueError, match="不能显式设置为 null"):
        TBSearchDataUpdate(**{field_name: None})


def test_tb_search_manual_update_allows_omitted_fields():
    from app.schemas.tb_search_data import TBSearchDataUpdate

    update = TBSearchDataUpdate()
    assert update.model_fields_set == set()
