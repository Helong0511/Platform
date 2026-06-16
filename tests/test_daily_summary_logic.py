"""
每日统计逻辑模拟测试：覆盖统计维度、筛选条件、分组与分页。

运行: pytest tests/test_daily_summary_logic.py -v
"""
from datetime import date

import pytest

from app.services.ad_data.queries.dimension_filter import (
    CROSS_DIMENSION,
    DEFAULT_DIMENSION,
    LEGACY_CROSS_DIMENSION,
    normalize_dimension,
)
from tests.daily_summary_simulator import (
    build_count_group_key,
    build_group_key,
    filter_raw_rows,
    row_matches_dimension,
    simulate_count_groups,
    simulate_daily_summary,
)

BASE_DATE = date(2026, 6, 1)


def _row(**kwargs):
    defaults = {
        "date": BASE_DATE,
        "product_id": 101,
        "product_name": "产品A",
        "client_id": 1,
        "client_name": "客户甲",
        "user_id": 10,
        "user_name": "张三",
        "product_active": True,
        "request_count": 100,
        "match_count": 80,
        "display_count": 50,
        "click_count": 10,
        "viewability_rate": 60.0,
        "cpc": 1.0,
        "pageviews": 200,
        "revenue_after_deduct": 25.0,
        "revenue_before_deduct": 30.0,
    }
    defaults.update(kwargs)
    return defaults


FIXTURE_ROWS = [
    _row(country_code="US", ad_unit="", request_count=100, match_count=80, display_count=50, click_count=10, revenue_after_deduct=20),
    _row(country_code="JP", ad_unit="", request_count=200, match_count=150, display_count=100, click_count=20, revenue_after_deduct=30),
    _row(country_code="ZZ", ad_unit="", request_count=50, match_count=40, display_count=20, click_count=4, revenue_after_deduct=5),
    _row(country_code="", ad_unit="slot-1", product_id=102, product_name="产品B", request_count=50, match_count=40, display_count=30, click_count=5, revenue_after_deduct=10),
    _row(country_code="", ad_unit="slot-2", product_id=102, product_name="产品B", request_count=60, match_count=50, display_count=40, click_count=6, revenue_after_deduct=12),
    _row(country_code="US", ad_unit="banner-x", product_id=103, product_name="产品C", request_count=30, match_count=20, display_count=10, click_count=2, revenue_after_deduct=5),
    _row(country_code="DE", ad_unit="banner-x", product_id=103, product_name="产品C", request_count=40, match_count=30, display_count=20, click_count=3, revenue_after_deduct=7),
    _row(country_code="ZZ", ad_unit="banner-z", product_id=103, product_name="产品C", request_count=15, match_count=10, display_count=5, click_count=1, revenue_after_deduct=2),
    _row(country_code="US", ad_unit="banner-y", product_id=103, product_name="产品C", request_count=10, match_count=8, display_count=5, click_count=1, revenue_after_deduct=2),
    _row(country_code="US", ad_unit="", product_id=201, product_name="产品D", client_id=2, client_name="客户乙", user_id=20, user_name="李四", request_count=80, match_count=60, display_count=40, click_count=8, revenue_after_deduct=16),
    _row(country_code="US", ad_unit="mixed", product_id=999, product_name="脏数据", request_count=1),
    _row(country_code="", ad_unit="", product_id=998, product_name="脏数据2", request_count=1),
]


class TestDimensionFilter:
    @pytest.mark.parametrize(
        "country,ad_unit,dimension,expected",
        [
            ("US", "", "country", True),
            ("JP", "", "country", True),
            ("ZZ", "", "country", True),
            ("AA", "", "country", True),
            ("ZZ", "slot-1", "country", False),
            ("US", "banner", "country", False),
            ("", "slot-1", "ad_unit", True),
            (None, "slot-1", "ad_unit", True),
            ("ZZ", "slot-1", "ad_unit", False),
            ("US", "slot-1", "ad_unit", False),
            ("US", "banner-x", CROSS_DIMENSION, True),
            ("ZZ", "banner-x", CROSS_DIMENSION, True),
            ("", "banner-x", CROSS_DIMENSION, False),
            ("US", "", CROSS_DIMENSION, False),
        ],
    )
    def test_row_matches_dimension(self, country, ad_unit, dimension, expected):
        row = _row(country_code=country, ad_unit=ad_unit)
        assert row_matches_dimension(row, dimension) is expected

    def test_normalize_legacy_alias(self):
        assert normalize_dimension(LEGACY_CROSS_DIMENSION) == CROSS_DIMENSION

    def test_invalid_dimension_defaults_country(self):
        assert normalize_dimension("invalid") == DEFAULT_DIMENSION


class TestCountryDimensionAggregation:
    def test_merges_all_countries_per_date_product_including_zz(self):
        data, total = simulate_daily_summary(FIXTURE_ROWS, dimension="country", product_id="101")
        assert total == 1
        row = data[0]
        assert row["request_count"] == 350
        assert row["revenue_after_deduct"] == 55.0
        assert row["country_code"] == "ZZ"

    def test_excludes_rows_with_ad_unit(self):
        filtered = filter_raw_rows(FIXTURE_ROWS, dimension="country")
        product_ids = {r["product_id"] for r in filtered}
        assert 999 not in product_ids


class TestAdUnitDimensionAggregation:
    def test_splits_by_ad_unit_without_country_code(self):
        data, total = simulate_daily_summary(FIXTURE_ROWS, dimension="ad_unit", product_id="102")
        assert total == 2
        assert all(not (r.get("country_code") or "").strip() for r in filter_raw_rows(FIXTURE_ROWS, dimension="ad_unit"))

    def test_zz_with_ad_unit_not_in_ad_unit_dimension(self):
        row = _row(country_code="ZZ", ad_unit="slot-x")
        assert row_matches_dimension(row, "ad_unit") is False
        assert row_matches_dimension(row, CROSS_DIMENSION) is True


class TestAdUnitCountryDimensionAggregation:
    def test_merges_countries_within_same_ad_unit(self):
        data, total = simulate_daily_summary(
            FIXTURE_ROWS, dimension=CROSS_DIMENSION, product_id="103"
        )
        assert total == 3
        banner_x = next(r for r in data if r["ad_unit"] == "banner-x")
        assert banner_x["request_count"] == 70


class TestFilters:
    def test_country_filter_zz(self):
        data, total = simulate_daily_summary(
            FIXTURE_ROWS,
            dimension="country",
            product_id="101",
            country_code="ZZ",
        )
        assert total == 1
        assert data[0]["request_count"] == 50

    def test_country_filter_on_cross_dimension(self):
        data, total = simulate_daily_summary(
            FIXTURE_ROWS,
            dimension=CROSS_DIMENSION,
            product_id="103",
            country_code="ZZ",
        )
        assert total == 1
        assert data[0]["ad_unit"] == "banner-z"


class TestCountGroupsConsistency:
    def test_count_matches_total_for_all_dimensions(self):
        for dim in ("country", "ad_unit", CROSS_DIMENSION):
            _, total = simulate_daily_summary(FIXTURE_ROWS, dimension=dim, page_size=1000)
            count = simulate_count_groups(FIXTURE_ROWS, dimension=dim)
            assert count == total, f"dimension={dim}"

    def test_count_group_key_includes_client(self):
        r1 = _row(client_id=1, country_code="US", ad_unit="")
        r2 = _row(client_id=2, product_id=101, country_code="US", ad_unit="")
        assert build_group_key(r1, "country") != build_group_key(r2, "country")
        assert build_count_group_key(r1, "country") != build_count_group_key(r2, "country")
