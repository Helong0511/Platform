"""广告数据统计维度筛选工具单元测试。"""
import pytest

from app.services.ad_data.queries.dimension_filter import (
    DEFAULT_DIMENSION,
    ensure_valid_optional_dimension,
    normalize_dimension,
    parse_optional_dimension,
)


class TestNormalizeDimension:
    def test_default_when_empty(self):
        assert normalize_dimension(None) == DEFAULT_DIMENSION
        assert normalize_dimension("") == DEFAULT_DIMENSION
        assert normalize_dimension("  ") == DEFAULT_DIMENSION

    def test_valid_values(self):
        assert normalize_dimension("country") == "country"
        assert normalize_dimension(" ad_unit ") == "ad_unit"
        assert normalize_dimension("country_ad_unit") == "country_ad_unit"

    def test_invalid_fallback(self):
        assert normalize_dimension("invalid") == DEFAULT_DIMENSION


class TestParseOptionalDimension:
    def test_none_when_not_provided(self):
        assert parse_optional_dimension(None) is None
        assert parse_optional_dimension("") is None
        assert parse_optional_dimension("   ") is None

    def test_valid_values(self):
        assert parse_optional_dimension("country") == "country"
        assert parse_optional_dimension(" ad_unit ") == "ad_unit"

    def test_invalid_returns_none(self):
        assert parse_optional_dimension("bad") is None


class TestEnsureValidOptionalDimension:
    def test_none_when_not_provided(self):
        assert ensure_valid_optional_dimension(None) is None
        assert ensure_valid_optional_dimension("") is None

    def test_valid_values(self):
        assert ensure_valid_optional_dimension("country_ad_unit") == "country_ad_unit"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="无效的 dimension"):
            ensure_valid_optional_dimension("bad")
