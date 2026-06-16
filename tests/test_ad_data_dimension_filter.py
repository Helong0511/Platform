"""广告数据统计维度筛选工具单元测试。"""
import pytest

from app.services.ad_data.queries.dimension_filter import (
    CROSS_DIMENSION,
    DEFAULT_DIMENSION,
    LEGACY_CROSS_DIMENSION,
    ensure_valid_optional_dimension,
    is_cross_dimension,
    normalize_dimension,
    parse_optional_dimension,
    row_has_country,
    row_has_no_country,
)


class TestNormalizeDimension:
    def test_default_when_empty(self):
        assert normalize_dimension(None) == DEFAULT_DIMENSION
        assert normalize_dimension("") == DEFAULT_DIMENSION
        assert normalize_dimension("  ") == DEFAULT_DIMENSION

    def test_valid_values(self):
        assert normalize_dimension("country") == "country"
        assert normalize_dimension(" ad_unit ") == "ad_unit"
        assert normalize_dimension(CROSS_DIMENSION) == CROSS_DIMENSION

    def test_legacy_cross_alias(self):
        assert normalize_dimension(LEGACY_CROSS_DIMENSION) == CROSS_DIMENSION

    def test_invalid_fallback(self):
        assert normalize_dimension("invalid") == DEFAULT_DIMENSION


class TestIsCrossDimension:
    def test_cross_and_legacy(self):
        assert is_cross_dimension(CROSS_DIMENSION) is True
        assert is_cross_dimension(LEGACY_CROSS_DIMENSION) is True
        assert is_cross_dimension("country") is False


class TestParseOptionalDimension:
    def test_none_when_not_provided(self):
        assert parse_optional_dimension(None) is None
        assert parse_optional_dimension("") is None
        assert parse_optional_dimension("   ") is None

    def test_valid_values(self):
        assert parse_optional_dimension("country") == "country"
        assert parse_optional_dimension(" ad_unit ") == "ad_unit"
        assert parse_optional_dimension(LEGACY_CROSS_DIMENSION) == CROSS_DIMENSION

    def test_invalid_returns_none(self):
        assert parse_optional_dimension("bad") is None


class TestEnsureValidOptionalDimension:
    def test_none_when_not_provided(self):
        assert ensure_valid_optional_dimension(None) is None
        assert ensure_valid_optional_dimension("") is None

    def test_valid_values(self):
        assert ensure_valid_optional_dimension(CROSS_DIMENSION) == CROSS_DIMENSION
        assert ensure_valid_optional_dimension(LEGACY_CROSS_DIMENSION) == CROSS_DIMENSION

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="无效的 dimension"):
            ensure_valid_optional_dimension("bad")


class TestCountryCodeSemantics:
    """有国家 / 无国家 行级语义（含 AA、ZZ）。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("US", True),
            ("AA", True),
            ("ZZ", True),
            ("", False),
            (None, False),
            ("  ", False),
        ],
    )
    def test_row_has_country(self, code, expected):
        assert row_has_country(code) is expected
        assert row_has_no_country(code) is (not expected)

    @pytest.mark.parametrize(
        "country,ad_unit,dimension,expected",
        [
            ("US", "", "country", True),
            ("ZZ", "", "country", True),
            ("AA", "", "country", True),
            ("", "slot-1", "ad_unit", True),
            (None, "slot-1", "ad_unit", True),
            ("ZZ", "slot-1", "ad_unit", False),
            ("ZZ", "slot-1", CROSS_DIMENSION, True),
            ("US", "banner", CROSS_DIMENSION, True),
            ("", "banner", CROSS_DIMENSION, False),
            ("US", "banner", "country", False),
        ],
    )
    def test_dimension_row_classification(self, country, ad_unit, dimension, expected):
        from tests.daily_summary_simulator import row_matches_dimension

        row = {"country_code": country, "ad_unit": ad_unit}
        assert row_matches_dimension(row, dimension) is expected
