"""
Telegram 统计周期解析。

将菜单选项（昨天、本周、上周、本月）映射为转化总览 API 使用的日期区间。
"""
from datetime import timedelta
from typing import Tuple

from app.core.utils import get_app_now_naive

# 菜单 callback_data 与展示名称
STATS_PERIOD_LABELS = {
    "stats_yesterday": "昨天",
    "stats_this_week": "本周",
    "stats_last_week": "上周",
    "stats_this_month": "本月",
}


def resolve_stats_date_range(period_key: str) -> Tuple[str, str, str]:
    """
    解析统计周期对应的起止日期（YYYY-MM-DD，含首尾日）。

    Args:
        period_key: stats_yesterday / stats_this_week / stats_last_week / stats_this_month

    Returns:
        (start_date, end_date, period_label)

    Raises:
        ValueError: 未知 period_key
    """
    if period_key not in STATS_PERIOD_LABELS:
        raise ValueError(f"未知统计周期: {period_key}")

    today = get_app_now_naive().date()
    label = STATS_PERIOD_LABELS[period_key]

    if period_key == "stats_yesterday":
        day = today - timedelta(days=1)
        return day.isoformat(), day.isoformat(), label

    if period_key == "stats_this_week":
        week_start = today - timedelta(days=today.weekday())
        return week_start.isoformat(), today.isoformat(), label

    if period_key == "stats_last_week":
        this_week_start = today - timedelta(days=today.weekday())
        last_week_end = this_week_start - timedelta(days=1)
        last_week_start = last_week_end - timedelta(days=6)
        return last_week_start.isoformat(), last_week_end.isoformat(), label

    # stats_this_month
    month_start = today.replace(day=1)
    return month_start.isoformat(), today.isoformat(), label
