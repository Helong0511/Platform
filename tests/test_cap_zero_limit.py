"""Zero Cap limits must reject conversions in both preflight and reservation paths."""
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
        self.flush_called = False

    async def execute(self, statement):
        return _Result(self.caps)

    async def flush(self):
        self.flush_called = True


def _cap(**overrides):
    values = {
        "id": 1,
        "cap_type": "offer",
        "advertiser_id": None,
        "offer_id": 10,
        "publisher_id": None,
        "daily_cap": None,
        "total_cap": None,
        "current_daily_count": 0,
        "current_total_count": 0,
        "cap_start_date": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "expected"),
    [("daily_cap", "每日Cap"), ("total_cap", "总Cap")],
)
async def test_check_cap_rejects_zero_limit(field, expected):
    db = _DB([_cap(**{field: 0})])

    allowed, reason = await cap_manager.check_cap(db, offer_id=10)

    assert allowed is False
    assert expected in reason


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["daily_cap", "total_cap"])
async def test_increment_cap_count_rejects_zero_before_redis_reservation(monkeypatch, field):
    async def unexpected_redis_call(*args, **kwargs):
        raise AssertionError("zero Cap must be rejected before Redis reservation")

    monkeypatch.setattr(
        cap_manager.RedisCapManager,
        "check_and_increment_daily",
        unexpected_redis_call,
    )
    monkeypatch.setattr(
        cap_manager.RedisCapManager,
        "check_and_increment_total",
        unexpected_redis_call,
    )
    monkeypatch.setattr(cap_manager, "_refresh_offer_caps", unexpected_redis_call)

    db = _DB([_cap(**{field: 0})])
    allowed, status = await cap_manager.increment_cap_count(db, offer_id=10)

    assert allowed is False
    assert status == "cap_exceeded"
    assert db.flush_called is False
