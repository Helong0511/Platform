"""Postback-to-ledger integration contracts for Redis Cap reservations."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.cap import cap_manager
from app.core.postback.checks.cap_checker import CapChecker
from app.core.postback.processor import PostbackProcessor


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Result:
    def __init__(self, rows=None):
        self.rows = rows or []

    def scalars(self):
        return _Scalars(self.rows)


class _DB:
    def __init__(self, caps):
        self.caps = caps
        self.flushed = False

    async def execute(self, statement):
        return _Result(self.caps)

    async def flush(self):
        self.flushed = True

    async def refresh(self, obj):
        return None


def _daily_cap():
    return SimpleNamespace(
        id=1,
        offer_id=77,
        publisher_id=12,
        daily_cap=100,
        total_cap=0,
        cap_start_date=None,
        current_daily_count=0,
        current_total_count=0,
    )


@pytest.mark.asyncio
async def test_postback_fail_open_keeps_prepared_ledger_for_commit_without_fake_redis_token(monkeypatch):
    cap = _daily_cap()
    db = _DB([cap])
    now = datetime(2026, 11, 11, 12, 0, 0)
    stable_key = "a" * 64
    prepare_calls = []
    redis_calls = []

    async def prepare(**kwargs):
        prepare_calls.append(kwargs)
        return SimpleNamespace(reservation_key=stable_key, state="PREPARED"), True, "lease-owner"

    async def daily(*args, **kwargs):
        redis_calls.append(kwargs)
        return None  # Redis unavailable + CAP_FAIL_OPEN

    async def mark_reserved(*args, **kwargs):
        raise AssertionError("fail-open must not be marked RESERVED")

    monkeypatch.setattr(cap_manager, "get_app_now_naive", lambda: now)
    monkeypatch.setattr(cap_manager.CapReservationLedger, "prepare_and_claim", prepare)
    monkeypatch.setattr(cap_manager.CapReservationLedger, "mark_reserved", mark_reserved)
    monkeypatch.setattr(cap_manager.RedisCapManager, "check_and_increment_daily", daily)

    ok, status, reservations = await cap_manager.increment_cap_count(
        db=db,
        offer_id=77,
        publisher_id=12,
        include_reservations=True,
        reservation_context={
            "platform": "isolated",
            "conversion_id": "conversion-77",
            "event_name": "purchase",
        },
    )

    assert (ok, status) == (True, "cap_ok")
    assert prepare_calls[0]["cap_kind"] == "daily"
    assert prepare_calls[0]["business_date"] == now.date()
    assert redis_calls[0]["reservation_id"] == stable_key
    assert len(reservations) == 1
    assert reservations[0][4:] == (stable_key, stable_key, "lease-owner", False)
    assert cap.current_daily_count == 1
    assert db.flushed is True


@pytest.mark.asyncio
async def test_postback_success_marks_ledger_reserved_with_stable_token(monkeypatch):
    cap = _daily_cap()
    db = _DB([cap])
    stable_key = "b" * 64
    marked = []
    redis_calls = []

    async def prepare(**kwargs):
        return SimpleNamespace(reservation_key=stable_key, state="PREPARED"), True, "owner-2"

    async def daily(*args, **kwargs):
        redis_calls.append(kwargs)
        return True

    async def mark_reserved(*args):
        marked.append(args)

    monkeypatch.setattr(
        cap_manager, "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    monkeypatch.setattr(cap_manager.CapReservationLedger, "prepare_and_claim", prepare)
    monkeypatch.setattr(cap_manager.CapReservationLedger, "mark_reserved", mark_reserved)
    monkeypatch.setattr(cap_manager.RedisCapManager, "check_and_increment_daily", daily)

    ok, status, reservations = await cap_manager.increment_cap_count(
        db=db,
        offer_id=77,
        publisher_id=12,
        include_reservations=True,
        reservation_context={
            "platform": "isolated",
            "conversion_id": "conversion-78",
            "event_name": "purchase",
        },
    )

    assert (ok, status) == (True, "cap_ok")
    assert redis_calls[0]["reservation_id"] == stable_key
    assert marked == [(stable_key, "owner-2")]
    assert reservations[0][7] is True


@pytest.mark.asyncio
async def test_duplicate_active_ledger_claim_rejects_second_redis_increment(monkeypatch):
    cap = _daily_cap()
    db = _DB([cap])
    redis_calls = []

    async def prepare(**kwargs):
        return SimpleNamespace(reservation_key="c" * 64, state="PREPARED"), False, None

    async def daily(*args, **kwargs):
        redis_calls.append(kwargs)
        return True

    monkeypatch.setattr(
        cap_manager, "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    monkeypatch.setattr(cap_manager.CapReservationLedger, "prepare_and_claim", prepare)
    monkeypatch.setattr(cap_manager.RedisCapManager, "check_and_increment_daily", daily)

    with pytest.raises(RuntimeError, match="已由其他请求处理"):
        await cap_manager.increment_cap_count(
            db=db,
            offer_id=77,
            publisher_id=12,
            include_reservations=True,
            reservation_context={
                "platform": "isolated",
                "conversion_id": "conversion-79",
                "event_name": "purchase",
            },
        )

    assert redis_calls == []


@pytest.mark.asyncio
async def test_fail_open_rollback_finalizes_ledger_without_redis_decrement(monkeypatch):
    redis_calls = []
    finalized = []

    async def decrement(*args, **kwargs):
        redis_calls.append((args, kwargs))
        return 0

    async def finalize(*args, **kwargs):
        finalized.append((args, kwargs))

    from app.core.postback.checks import cap_checker
    monkeypatch.setattr(cap_checker.RedisCapManager, "decrement_daily", decrement)
    monkeypatch.setattr(cap_checker.CapReservationLedger, "finalize", finalize)

    await CapChecker.rollback_reservations([
        ("daily", 77, 12, datetime(2026, 11, 11), "d" * 64, "d" * 64, "owner", False)
    ])

    assert redis_calls == []
    assert finalized[0][0] == ("d" * 64, "ROLLED_BACK")
    assert finalized[0][1]["lease_owner"] == "owner"


@pytest.mark.asyncio
async def test_postback_commit_finalizes_ledger_after_database_commit(monkeypatch):
    calls = []

    class FakeDB:
        async def commit(self):
            calls.append("db_commit")

    async def finalize(*args, **kwargs):
        calls.append(("ledger_finalize", args, kwargs))

    async def renew_lease(*args, **kwargs):
        return None

    from app.core.postback import processor as processor_module
    monkeypatch.setattr(processor_module.CapReservationLedger, "finalize", finalize)
    monkeypatch.setattr(processor_module.CapReservationLedger, "renew_lease", renew_lease)

    await PostbackProcessor._commit_conversion_with_cap_reconciliation(
        db=FakeDB(),
        conversion_id=9001,
        cap_reservations=[
            ("daily", 77, 12, datetime(2026, 11, 11), "e" * 64, "e" * 64, "owner", True)
        ],
    )

    assert calls[0] == "db_commit"
    assert calls[1] == (
        "ledger_finalize",
        ("e" * 64, "COMMITTED"),
        {"lease_owner": "owner"},
    )



@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token_value", "counter_value", "expected"),
    [
        (b"1", b"7", "PRESENT"),
        (None, b"7", "ABSENT"),
        (b"1", None, "UNKNOWN"),
        (b"1", b"not-a-number", "UNKNOWN"),
    ],
)
async def test_redis_reservation_token_state_is_three_valued(
    monkeypatch, token_value, counter_value, expected
):
    from app.core.cap import redis_counter

    class FakeRedis:
        async def mget(self, *keys):
            assert keys == ("counter:key:reservation:token", "counter:key")
            return [token_value, counter_value]

    async def get_redis():
        return FakeRedis()

    monkeypatch.setattr(redis_counter, "get_redis_client", get_redis)

    state = await redis_counter.RedisCapManager.get_reservation_token_state(
        "counter:key", "counter:key:reservation:token"
    )

    assert state == expected


@pytest.mark.asyncio
async def test_redis_reservation_token_state_is_unknown_when_redis_unavailable(monkeypatch):
    from app.core.cap import redis_counter

    async def get_redis():
        return None

    monkeypatch.setattr(redis_counter, "get_redis_client", get_redis)

    state = await redis_counter.RedisCapManager.get_reservation_token_state(
        "counter:key", "counter:key:reservation:token"
    )

    assert state == "UNKNOWN"


@pytest.mark.asyncio
async def test_recovery_rollback_uses_exact_persisted_redis_keys(monkeypatch):
    from app.core.cap import redis_counter

    calls = []

    class FakeRedis:
        async def eval(self, script, numkeys, *keys):
            calls.append((script, numkeys, keys))
            return 4

    async def get_redis():
        return FakeRedis()

    monkeypatch.setattr(redis_counter, "get_redis_client", get_redis)

    result = await redis_counter.RedisCapManager.rollback_reservation_keys(
        "persisted:counter:key", "persisted:token:key"
    )

    assert result == 4
    assert calls == [(
        redis_counter.RedisCapManager._ROLLBACK_RESERVATION_LUA,
        2,
        ("persisted:counter:key", "persisted:token:key"),
    )]
