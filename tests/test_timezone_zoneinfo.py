"""时区实现必须使用标准库 zoneinfo，避免依赖已弃用的 pytz。"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.utils import APP_TIMEZONE, get_app_now, get_app_now_naive
from app.schemas.base import datetime_encoder


def test_app_timezone_uses_zoneinfo():
    assert isinstance(APP_TIMEZONE, ZoneInfo)


def test_app_now_returns_aware_datetime_and_naive_helper_is_naive():
    aware = get_app_now()
    naive = get_app_now_naive()

    assert aware.tzinfo is APP_TIMEZONE
    assert naive.tzinfo is None


def test_datetime_encoder_attaches_configured_timezone_to_naive_value():
    value = datetime(2026, 1, 15, 12, 30, 0)

    encoded = datetime_encoder(value)
    expected = value.replace(tzinfo=APP_TIMEZONE).isoformat()

    assert encoded == expected
