"""TBSJ 日期格式与分页终止条件测试。"""
from app.scheduler_module.upstream_fetch import format_tbsj_datetime_range


def test_format_tbsj_datetime_range_single_day():
    start, end = format_tbsj_datetime_range("2026-06-13", "2026-06-13")
    assert start == "2026-06-13 00:00:00"
    assert end == "2026-06-13 23:59:59"


def test_format_tbsj_datetime_range_cross_day():
    start, end = format_tbsj_datetime_range("2026-06-12", "2026-06-13")
    assert start == "2026-06-12 00:00:00"
    assert end == "2026-06-13 23:59:59"
