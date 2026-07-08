"""上游入库报表类型自动推断与 Telegram 文案格式化测试。"""
from app.core.ad_data_metadata import (
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_CROSS,
    REPORT_TYPE_DAILY,
    REPORT_TYPE_UNIT,
    format_report_type_counts_for_notify,
    infer_report_type_from_shape,
    resolve_report_type_for_row,
)


def test_infer_report_type_country_only():
    assert infer_report_type_from_shape(ad_unit="", country_code="US") == REPORT_TYPE_COUNTRY


def test_infer_report_type_unit_only():
    assert infer_report_type_from_shape(ad_unit="banner_1", country_code="") == REPORT_TYPE_UNIT


def test_infer_report_type_cross():
    assert (
        infer_report_type_from_shape(ad_unit="banner_1", country_code="US")
        == REPORT_TYPE_CROSS
    )


def test_infer_report_type_daily():
    assert infer_report_type_from_shape(ad_unit="", country_code=None) == REPORT_TYPE_DAILY


def test_resolve_report_type_ignores_explicit():
    """显式传入 unit 时仍按行形态推断为 cross。"""
    assert (
        resolve_report_type_for_row(
            REPORT_TYPE_UNIT,
            ad_unit="slot_a",
            country_code="CN",
        )
        == REPORT_TYPE_CROSS
    )


def test_format_report_type_counts_for_notify_single():
    text = format_report_type_counts_for_notify({REPORT_TYPE_COUNTRY: 12})
    assert text == "国家(country) 12条"


def test_format_report_type_counts_for_notify_mixed():
    text = format_report_type_counts_for_notify(
        {REPORT_TYPE_COUNTRY: 8, REPORT_TYPE_CROSS: 4}
    )
    assert text == "国家(country) 8条、交叉(cross) 4条"


def test_format_report_type_counts_for_notify_empty():
    assert format_report_type_counts_for_notify({}) == ""
    assert format_report_type_counts_for_notify(None) == ""
