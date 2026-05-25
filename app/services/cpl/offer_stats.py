"""
Offer 统计周期与趋势计算（供 API 与单测复用）
"""
from datetime import timedelta

from app.core.utils import get_app_now_naive


def offer_stats_period_start(period: str):
    """按 day/week/month 计算统计区间起点（应用本地 naive 时间）。"""
    now = get_app_now_naive()
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)


def offer_stats_previous_range(period: str, current_start):
    """上一对比区间 [start, end)。"""
    if period == "day":
        prev_end = current_start
        return current_start - timedelta(days=1), prev_end
    if period == "month":
        prev_end = current_start
        if current_start.month == 1:
            prev_start = current_start.replace(year=current_start.year - 1, month=12)
        else:
            prev_start = current_start.replace(month=current_start.month - 1)
        return prev_start, prev_end
    prev_end = current_start
    return current_start - timedelta(days=7), prev_end


def pct_trend(current: float, previous: float) -> float:
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 2)
