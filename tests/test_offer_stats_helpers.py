"""Offer 统计周期辅助函数单测"""
from datetime import timedelta

from app.services.cpl.offer_stats import (
    offer_stats_period_start,
    offer_stats_previous_range,
    pct_trend,
)


def test_pct_trend_from_zero_previous():
    assert pct_trend(10, 0) == 100.0
    assert pct_trend(0, 0) == 0.0


def test_pct_trend_normal():
    assert pct_trend(150, 100) == 50.0


def test_week_period_start_is_seven_day_window():
    start = offer_stats_period_start("week")
    assert start.hour == 0
    assert start.minute == 0


def test_previous_range_day():
    start = offer_stats_period_start("day")
    prev_start, prev_end = offer_stats_previous_range("day", start)
    assert prev_end == start
    assert prev_start == start - timedelta(days=1)
