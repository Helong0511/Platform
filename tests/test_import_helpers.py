"""Excel 导入 helpers 单元测试"""
import pytest

from app.api_v1.excel.import_handler import clean_numeric_value


def test_clean_numeric_value_plain():
    assert clean_numeric_value(10) == 10.0
    assert clean_numeric_value("3.5") == 3.5


def test_clean_numeric_value_percent():
    assert clean_numeric_value("10%") == 10.0
    assert clean_numeric_value("100.00%") == 100.0


def test_clean_numeric_value_none_raises():
    with pytest.raises(ValueError):
        clean_numeric_value(None)
