"""上游任务日期范围解析"""
from unittest.mock import patch
from datetime import datetime

import pytz

from app.scheduler_module.task_utils import resolve_upstream_date_range, APP_TIMEZONE


def test_resolve_explicit_dates():
    assert resolve_upstream_date_range("2026-01-01", "2026-01-03") == (
        "2026-01-01",
        "2026-01-03",
    )
    assert resolve_upstream_date_range("2026-01-01", None) == ("2026-01-01", "2026-01-01")


@patch("app.scheduler_module.task_utils.datetime")
def test_resolve_early_morning_dual_day(mock_dt):
    fixed = datetime(2026, 5, 20, 1, 30, tzinfo=APP_TIMEZONE)
    mock_dt.now.return_value = fixed
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    start, end = resolve_upstream_date_range(early_morning_dual_day=True)
    assert start == "2026-05-19"
    assert end == "2026-05-20"


@patch("app.scheduler_module.task_utils.datetime")
def test_resolve_same_day_default(mock_dt):
    fixed = datetime(2026, 5, 20, 10, 0, tzinfo=APP_TIMEZONE)
    mock_dt.now.return_value = fixed
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    start, end = resolve_upstream_date_range()
    assert start == end == "2026-05-20"
