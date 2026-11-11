"""Multiple Cap rules backed by one Redis key must count a conversion once."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.cap import cap_manager


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return _Scalars(self.rows)


class _DB:
    def __init__(self, caps):
        self.caps = caps
        self.flushed = False
        self.query = None

    async def execute(self, statement):
        self.query = statement
        return _Result(self.caps)

    async def flush(self):
        self.flushed = True


@pytest.mark.asyncio
async def test_overlapping_offer_and_advertiser_caps_reserve_shared_key_once(monkeypatch):
    now = datetime(2026, 11, 10, 12, 0, 0)
    caps = [
        SimpleNamespace(
            id=1, cap_type="offer", advertiser_id=None, offer_id=77, publisher_id=12,
            daily_cap=100, total_cap=500, cap_start_date=now,
            current_daily_count=5, current_total_count=10,
        ),
        SimpleNamespace(
            id=2, cap_type="advertiser_offer", advertiser_id=7, offer_id=77, publisher_id=12,
            daily_cap=80, total_cap=400, cap_start_date=now,
            current_daily_count=4, current_total_count=9,
        ),
    ]
    db = _DB(caps)
    daily_calls = []
    total_calls = []

    async def reserve_daily(offer_id, limit, publisher_id=None, **kwargs):
        daily_calls.append((offer_id, limit, publisher_id, kwargs))
        return True

    async def reserve_total(offer_id, limit, publisher_id=None, **kwargs):
        total_calls.append((offer_id, limit, publisher_id, kwargs))
        return True

    monkeypatch.setattr(cap_manager, "get_app_now_naive", lambda: now)
    monkeypatch.setattr(cap_manager.settings, "CAP_FAIL_OPEN", False)
    monkeypatch.setattr(cap_manager.RedisCapManager, "check_and_increment_daily", reserve_daily)
    monkeypatch.setattr(cap_manager.RedisCapManager, "check_and_increment_total", reserve_total)

    ok, status, reservations = await cap_manager.increment_cap_count(
        db,
        offer_id=77,
        publisher_id=12,
        advertiser_id=7,
        include_reservations=True,
    )

    assert ok is True
    assert status == "cap_ok"
    assert len(daily_calls) == 1
    assert len(total_calls) == 1
    assert daily_calls[0][1] == 80
    assert daily_calls[0][3]["initial_value"] == 5
    assert total_calls[0][1] == 400
    assert total_calls[0][3]["initial_value"] == 10
    assert len(reservations) == 2
    assert all(cap.current_daily_count == 6 for cap in caps)
    assert all(cap.current_total_count == 11 for cap in caps)
    assert all(cap.cap_start_date == datetime(2026, 11, 10, 0, 0, 0) for cap in caps)
    assert db.flushed is True
    assert str(db.query._order_by_clauses[0]) == "offer_caps.id ASC"
