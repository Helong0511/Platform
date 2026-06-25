"""广告数据多选筛选参数解析测试。"""
import pytest

from app.services.ad_data.queries.filter_conditions import (
    InvalidFilterParameterError,
    apply_client_ids_filter,
    apply_product_ids_filter,
    build_ad_units_in_filter,
    parse_csv_ints,
    parse_csv_strs,
)


def test_parse_csv_ints_single_and_multi():
    assert parse_csv_ints(5) == [5]
    assert parse_csv_ints("1,2,3") == [1, 2, 3]
    assert parse_csv_ints("") is None
    assert parse_csv_ints(None) is None


def test_parse_csv_ints_rejects_non_numeric():
    with pytest.raises(InvalidFilterParameterError) as exc_info:
        parse_csv_ints("1,abc", field="client_id")
    assert exc_info.value.field == "client_id"
    assert exc_info.value.invalid_part == "abc"
    assert "client_id" in str(exc_info.value)


def test_parse_csv_strs():
    assert parse_csv_strs("US,CN") == ["US", "CN"]
    assert parse_csv_strs(" unit-a , unit-b ") == ["unit-a", "unit-b"]


def test_in_filters():
    from sqlalchemy import column

    client_col = column("client_id")
    product_col = column("product_id")
    ad_unit_col = column("ad_unit")

    single = apply_client_ids_filter(client_col, [1])
    assert "IN" not in str(single).upper()

    multi = apply_client_ids_filter(client_col, [1, 2])
    assert "IN" in str(multi).upper()

    assert apply_product_ids_filter(product_col, [10, 11]) is not None
    assert build_ad_units_in_filter(ad_unit_col, ["a", "b"]) is not None
