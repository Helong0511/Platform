"""明细维度（data_type=all）字段形态筛选规则单元测试。"""
from app.services.ad_data.queries.dimension_filter import (
    row_is_ad_unit_only,
    row_is_country_only,
    row_is_cross_row,
    row_is_plain_summary,
)


def test_country_only_shape():
    assert row_is_country_only("US", "") is True
    assert row_is_country_only("US", None) is True
    assert row_is_country_only("AA", "") is True
    assert row_is_country_only("", "unit_a") is False
    assert row_is_country_only("US", "unit_a") is False


def test_ad_unit_only_shape():
    assert row_is_ad_unit_only("", "banner_1") is True
    assert row_is_ad_unit_only(None, "banner_1") is True
    assert row_is_ad_unit_only("US", "banner_1") is False
    assert row_is_ad_unit_only("", "") is False


def test_cross_shape():
    assert row_is_cross_row("AE", "food.fanquer.com_anchor") is True
    assert row_is_cross_row("US", "") is False
    assert row_is_cross_row("", "banner_1") is False


def test_plain_summary_not_country_or_ad_unit():
    assert row_is_plain_summary("", "") is True
    assert row_is_country_only("", "") is False
    assert row_is_ad_unit_only("", "") is False
