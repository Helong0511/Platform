"""扣减统计日期范围必须遵循应用时区时钟。"""
from datetime import datetime, timedelta

from app.services.cpl.deduction.queries.stats_query import DeductionStatsQuery


def test_default_date_range_uses_application_clock(monkeypatch):
    app_now = datetime(2026, 11, 28, 9, 30, 0)
    monkeypatch.setattr(
        "app.services.cpl.deduction.queries.stats_query.get_app_now_naive",
        lambda: app_now,
    )

    start_dt, end_dt = DeductionStatsQuery(db=None)._parse_date_range(None, None)

    assert end_dt == app_now
    assert start_dt == app_now - timedelta(days=30)


def test_missing_end_date_uses_application_clock(monkeypatch):
    app_now = datetime(2026, 11, 28, 9, 30, 0)
    monkeypatch.setattr(
        "app.services.cpl.deduction.queries.stats_query.get_app_now_naive",
        lambda: app_now,
    )

    start_dt, end_dt = DeductionStatsQuery(db=None)._parse_date_range(
        "2026-11-01", None
    )

    assert start_dt == datetime(2026, 11, 1, 0, 0, 0)
    assert end_dt == app_now
