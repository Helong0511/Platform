"""Cap reservation 精确回滚与 COMMIT 不确定结果回归测试。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.cap import cap_manager
from app.core.postback.checks import cap_checker
from app.core.postback.checks.cap_checker import CapChecker
from app.core.postback.processor import PostbackProcessor


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Result:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or []
        self.scalar = scalar

    def scalars(self):
        return _Scalars(self.rows)

    def scalar_one_or_none(self):
        return self.scalar


class _FakeCapDB:
    def __init__(self, caps):
        self.caps = caps
        self.flushed = False
        self.refreshed = []

    async def execute(self, statement):
        return _Result(rows=self.caps)

    async def flush(self):
        self.flushed = True

    async def refresh(self, obj):
        self.refreshed.append(obj)


@pytest.mark.asyncio
async def test_fail_open_only_returns_reservations_that_really_incremented(monkeypatch):
    cap = SimpleNamespace(
        offer_id=77,
        publisher_id=12,
        daily_cap=100,
        total_cap=1000,
        cap_start_date=None,
        current_daily_count=0,
        current_total_count=5,
    )
    db = _FakeCapDB([cap])

    async def daily_fails(*args, **kwargs):
        raise OSError("isolated Redis daily counter failure")

    async def total_succeeds(*args, **kwargs):
        return True

    monkeypatch.setattr(cap_manager.settings, "CAP_FAIL_OPEN", True)
    monkeypatch.setattr(
        cap_manager.RedisCapManager,
        "check_and_increment_daily",
        daily_fails,
    )
    monkeypatch.setattr(
        cap_manager.RedisCapManager,
        "check_and_increment_total",
        total_succeeds,
    )

    ok, status, reservations = await cap_manager.increment_cap_count(
        db=db,
        offer_id=77,
        publisher_id=12,
        include_reservations=True,
    )

    assert ok is True
    assert status == "cap_ok"
    assert reservations == [("total", 77, 12)]
    assert db.flushed is True


@pytest.mark.asyncio
async def test_cap_checker_rolls_back_only_the_recorded_reservations(monkeypatch):
    calls = []

    async def dec_daily(offer_id, publisher_id=None):
        calls.append(("daily", offer_id, publisher_id))

    async def dec_total(offer_id, publisher_id=None):
        calls.append(("total", offer_id, publisher_id))

    monkeypatch.setattr(cap_checker.RedisCapManager, "decrement_daily", staticmethod(dec_daily))
    monkeypatch.setattr(cap_checker.RedisCapManager, "decrement_total", staticmethod(dec_total))

    await CapChecker.rollback_reservations([("total", 77, 12)])

    assert calls == [("total", 77, 12)]


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_reservation_only_when_conversion_absent(monkeypatch):
    calls = []

    class FakeDB:
        def __init__(self, persisted):
            self.persisted = persisted
            self.rollback_calls = 0

        async def commit(self):
            raise OSError("simulated isolated commit response failure")

        async def rollback(self):
            self.rollback_calls += 1

        async def execute(self, statement):
            return _Result(scalar=101 if self.persisted else None)

    async def rollback_reservations(reservations):
        calls.append(list(reservations))

    monkeypatch.setattr(
        CapChecker,
        "rollback_reservations",
        rollback_reservations,
    )
    reservations = [("daily", 77, 12)]

    with pytest.raises(OSError):
        await PostbackProcessor._commit_conversion_with_cap_reconciliation(
            db=FakeDB(persisted=False),
            conversion_id=101,
            cap_reservations=reservations,
        )
    assert calls == [reservations]

    calls.clear()
    with pytest.raises(OSError):
        await PostbackProcessor._commit_conversion_with_cap_reconciliation(
            db=FakeDB(persisted=True),
            conversion_id=101,
            cap_reservations=reservations,
        )
    assert calls == []
