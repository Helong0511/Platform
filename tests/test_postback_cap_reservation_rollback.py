"""Cap reservation 精确回滚与 COMMIT 不确定结果回归测试。"""
from __future__ import annotations

from datetime import datetime
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
    assert reservations == [("total", 77, 12, None)]
    assert db.flushed is True


@pytest.mark.asyncio
async def test_cap_checker_rolls_back_only_the_recorded_reservations(monkeypatch):
    calls = []

    async def dec_daily(offer_id, publisher_id=None, reservation_date=None):
        calls.append(("daily", offer_id, publisher_id, reservation_date))

    async def dec_total(offer_id, publisher_id=None):
        calls.append(("total", offer_id, publisher_id, None))

    monkeypatch.setattr(cap_checker.RedisCapManager, "decrement_daily", staticmethod(dec_daily))
    monkeypatch.setattr(cap_checker.RedisCapManager, "decrement_total", staticmethod(dec_total))

    reservation_date = datetime(2026, 11, 9, 0, 0, 0)
    await CapChecker.rollback_reservations([
        ("daily", 77, 12, reservation_date),
        ("total", 77, 12, None),
    ])

    assert calls == [
        ("daily", 77, 12, reservation_date),
        ("total", 77, 12, None),
    ]


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
    reservations = [("daily", 77, 12, datetime(2026, 11, 9))]

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



@pytest.mark.asyncio
async def test_daily_cap_rollback_uses_original_reservation_date(monkeypatch):
    from app.core.cap import redis_counter

    calls = []

    class FakeRedis:
        async def eval(self, script, number_of_keys, key):
            calls.append(key)
            return 0

    async def fake_get_redis_client():
        return FakeRedis()

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(
        redis_counter,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 10, 0, 1, 0),
    )

    await redis_counter.RedisCapManager.decrement_daily(
        offer_id=77,
        publisher_id=12,
        reservation_date=datetime(2026, 11, 9, 0, 0, 0),
    )

    assert len(calls) == 1
    assert ":daily:77:2026-11-09:pub:12" in calls[0]



@pytest.mark.asyncio
async def test_successful_daily_reservation_records_business_date(monkeypatch):
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

    async def daily_succeeds(*args, **kwargs):
        return True

    async def total_succeeds(*args, **kwargs):
        return True

    business_now = datetime(2026, 11, 10, 12, 30, 0)
    monkeypatch.setattr(cap_manager, "get_app_now_naive", lambda: business_now)
    monkeypatch.setattr(
        cap_manager.RedisCapManager,
        "check_and_increment_daily",
        daily_succeeds,
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
    assert reservations == [
        ("daily", 77, 12, datetime(2026, 11, 10, 0, 0, 0)),
        ("total", 77, 12, None),
    ]


@pytest.mark.asyncio
async def test_postback_precommit_queue_failure_rolls_back_cap_reservation_once(monkeypatch):
    from decimal import Decimal
    from app.core.postback import processor as processor_module
    from app.core.postback import handlers as handlers_module

    reservations = [("daily", 77, 12, datetime(2026, 11, 10))]
    rollback_calls = []

    class FakeDB:
        def __init__(self):
            self.rollback_calls = 0

        async def rollback(self):
            self.rollback_calls += 1

    class FakeHandler:
        async def validate(self, raw_data):
            return True, None

        async def normalize(self, raw_data):
            return {
                "platform": "isolated-test",
                "conversion_id": "conversion-101",
                "event_name": "purchase",
                "click_id": "click-101",
            }

    async def valid_ip(*args, **kwargs):
        return True, "203.0.113.10"

    async def associate(ctx):
        ctx.click_association = {
            "offer_id": 77,
            "publisher_id": 12,
            "advertiser_id": None,
            "click_id": "click-101",
        }
        return ctx.click_association

    async def valid_offer(ctx):
        return True

    async def not_duplicate(ctx):
        return False

    async def apply_discount(ctx):
        return Decimal("1.00"), {}, False

    async def reserve(**kwargs):
        return True, "cap_ok", reservations

    async def save_conversion(ctx):
        return SimpleNamespace(id=101, product_id=None, conversion_id='conversion-101')

    async def fail_enqueue(**kwargs):
        raise OSError("simulated isolated queue insert failure")

    async def rollback_reservations(items):
        rollback_calls.append(list(items))

    monkeypatch.setattr(processor_module.IpValidator, "validate", staticmethod(valid_ip))
    monkeypatch.setattr(handlers_module, "get_handler", lambda platform: FakeHandler())
    monkeypatch.setattr(processor_module, "step_associate_click", associate)
    monkeypatch.setattr(processor_module, "step_validate_offer_status", valid_offer)
    monkeypatch.setattr(processor_module, "step_check_duplicate", not_duplicate)
    monkeypatch.setattr(processor_module, "step_apply_discount", apply_discount)
    monkeypatch.setattr(processor_module.CapChecker, "increment_with_reservations", reserve)
    monkeypatch.setattr(processor_module, "step_save_conversion", save_conversion)
    monkeypatch.setattr(
        processor_module.PostbackProcessor,
        "_enqueue_downstream_forward_tasks",
        fail_enqueue,
    )
    monkeypatch.setattr(processor_module.CapChecker, "rollback_reservations", rollback_reservations)

    db = FakeDB()
    with pytest.raises(OSError, match="queue insert failure"):
        await PostbackProcessor.process(
            platform="isolated-test",
            raw_data={"conversion_id": "conversion-101"},
            db=db,
            request_ip="203.0.113.10",
        )

    assert rollback_calls == [reservations]
    assert db.rollback_calls == 1
