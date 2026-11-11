"""Cap preflight checks must be read-only and must not undercount confirmed DB usage."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.cap import cap_manager


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _DB:
    def __init__(self, cap):
        self.cap = cap

    async def execute(self, _statement):
        return _Result([self.cap])


class _Redis:
    def __init__(self, values):
        self.values = values
        self.writes = []

    async def get(self, key):
        return self.values.get(key)

    async def set(self, *args, **kwargs):
        self.writes.append((args, kwargs))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("daily", "total", "redis_daily", "redis_total", "expected"),
    [
        (8, 0, "3", None, False),
        (0, 12, None, "4", False),
        (8, 0, None, None, False),
        (0, 12, None, None, False),
    ],
)
async def test_preflight_uses_db_floor_and_never_recreates_missing_redis_keys(
    monkeypatch, daily, total, redis_daily, redis_total, expected
):
    now = datetime(2026, 11, 10, 12, 0, 0)
    cap = SimpleNamespace(
        offer_id=901,
        publisher_id=33,
        advertiser_id=None,
        cap_type="offer",
        is_active=True,
        daily_cap=8 if daily else None,
        total_cap=12 if total else None,
        cap_start_date=now,
        current_daily_count=daily,
        current_total_count=total,
    )
    daily_key = cap_manager.get_daily_cap_key(901, now, 33)
    total_key = cap_manager.get_total_cap_key(901, 33)
    values = {}
    if redis_daily is not None:
        values[daily_key] = redis_daily
    if redis_total is not None:
        values[total_key] = redis_total
    redis = _Redis(values)

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_manager, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_manager, "get_app_now_naive", lambda: now)
    monkeypatch.setattr(cap_manager.settings, "CAP_FAIL_OPEN", False)

    allowed, _reason = await cap_manager.check_cap(
        db=_DB(cap),
        offer_id=901,
        publisher_id=33,
    )

    assert allowed is expected
    assert redis.writes == []

@pytest.mark.asyncio
async def test_preflight_refreshes_daily_business_date_together_with_redis_key(monkeypatch):
    """预检查跨午夜时，Redis key 与 DB 日计数必须使用同一业务日期。"""
    clock = iter([
        datetime(2026, 11, 10, 23, 59, 59),
        datetime(2026, 11, 11, 0, 0, 1),
    ])
    cap = SimpleNamespace(
        offer_id=902,
        publisher_id=34,
        advertiser_id=None,
        cap_type="offer",
        is_active=True,
        daily_cap=8,
        total_cap=None,
        cap_start_date=datetime(2026, 11, 10, 0, 0, 0),
        current_daily_count=8,
        current_total_count=0,
    )
    redis = _Redis({})

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_manager, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_manager, "get_app_now_naive", lambda: next(clock))
    monkeypatch.setattr(cap_manager.settings, "CAP_FAIL_OPEN", False)

    allowed, reason = await cap_manager.check_cap(
        db=_DB(cap),
        offer_id=902,
        publisher_id=34,
    )

    # key 已切换到 11 月 11 日，昨日 DB=8 不能错误地阻止今日请求。
    assert allowed is True
    assert reason is None
    assert redis.writes == []

