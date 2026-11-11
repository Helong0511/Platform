"""Crash recovery worker safety tests; all storage clients are isolated mocks."""
from types import SimpleNamespace

import pytest

from app.services import cap_reservation_recovery as recovery


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows=None, event_id=None):
        self.rows = rows or []
        self.event_id = event_id
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return _Rows(self.rows)

    async def scalar(self, statement):
        return self.event_id

    async def commit(self):
        self.commits += 1


def _reservation(*, state="PREPARED", redis_reserved=False, redis_token_cleaned=False):
    return SimpleNamespace(
        id=1,
        reservation_key="f" * 64,
        platform="isolated",
        conversion_id="conversion-1",
        event_name="purchase",
        offer_id=77,
        publisher_id=12,
        cap_kind="daily",
        business_date=None,
        redis_counter_key="counter:key",
        redis_token_key="counter:key:reservation:" + "f" * 64,
        redis_reserved=redis_reserved,
        redis_token_cleaned=redis_token_cleaned,
        state=state,
        attempts=0,
        lease_owner=None,
        lease_expires_at=None,
        prepared_at=None,
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_recovery_rolls_back_token_created_before_reserved_marker(monkeypatch):
    row = _reservation(redis_reserved=False)
    sessions = [_Session(rows=[row]), _Session(event_id=None)]
    calls = []

    def session_factory():
        return sessions.pop(0)

    async def token_state(counter_key, token_key):
        return "PRESENT"

    async def rollback(counter_key, token_key):
        calls.append(("rollback", counter_key, token_key))
        return 3

    async def finalize(key, state, **kwargs):
        calls.append(("finalize", key, state, kwargs))

    monkeypatch.setattr(recovery, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(recovery.RedisCapManager, "get_reservation_token_state", token_state)
    monkeypatch.setattr(recovery.RedisCapManager, "rollback_reservation_keys", rollback)
    monkeypatch.setattr(recovery.CapReservationLedger, "finalize", finalize)

    stats = await recovery.recover_cap_reservations()

    assert stats["rolled_back"] == 1
    assert calls[0] == ("rollback", "counter:key", row.redis_token_key)
    assert calls[1][0:3] == ("finalize", row.reservation_key, "ROLLED_BACK")
    assert calls[1][3]["lease_owner"] == row.lease_owner


@pytest.mark.asyncio
async def test_recovery_does_not_decrement_when_reserved_token_is_absent(monkeypatch):
    row = _reservation(state="RESERVED", redis_reserved=True)
    sessions = [_Session(rows=[row]), _Session(event_id=None)]
    calls = []

    def session_factory():
        return sessions.pop(0)

    async def token_state(counter_key, token_key):
        return "ABSENT"

    async def mark_needs(key, error, **kwargs):
        calls.append((key, error, kwargs))

    async def forbidden_rollback(*args):
        raise AssertionError("ABSENT token must never cause DECR")

    monkeypatch.setattr(recovery, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(recovery.RedisCapManager, "get_reservation_token_state", token_state)
    monkeypatch.setattr(recovery.RedisCapManager, "rollback_reservation_keys", forbidden_rollback)
    monkeypatch.setattr(recovery.CapReservationLedger, "mark_needs_reconciliation", mark_needs)

    stats = await recovery.recover_cap_reservations()

    assert stats["needs_reconciliation"] == 1
    assert calls[0][0] == row.reservation_key
    assert "token ABSENT" in calls[0][1]


@pytest.mark.asyncio
async def test_recovery_retries_needs_reconciliation_after_backoff(monkeypatch):
    """Redis 短暂不可用进入 NEEDS_RECONCILIATION 后，恢复可用时必须自动重试。"""
    from datetime import datetime
    from sqlalchemy.dialects import mysql

    row = _reservation(state="NEEDS_RECONCILIATION")
    row.updated_at = datetime(2026, 11, 11, 11, 50, 0)
    sessions = [_Session(rows=[row]), _Session(event_id=None)]
    captured = {}
    calls = []

    class QuerySession(_Session):
        async def execute(self, statement):
            captured["sql"] = str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})).lower()
            return _Rows(self.rows)

    def session_factory():
        return QuerySession(rows=[row]) if len(sessions) == 2 and not captured else sessions.pop(0)

    async def token_state(counter_key, token_key):
        return "PRESENT"

    async def rollback(counter_key, token_key):
        calls.append(("rollback", counter_key, token_key))
        return 1

    async def finalize(key, state, **kwargs):
        calls.append(("finalize", key, state, kwargs))

    monkeypatch.setattr(recovery, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(
        recovery, "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )
    monkeypatch.setattr(recovery.RedisCapManager, "get_reservation_token_state", token_state)
    monkeypatch.setattr(recovery.RedisCapManager, "rollback_reservation_keys", rollback)
    monkeypatch.setattr(recovery.CapReservationLedger, "finalize", finalize)

    stats = await recovery.recover_cap_reservations()

    assert "needs_reconciliation" in captured["sql"]
    assert "updated_at" in captured["sql"]
    assert stats["rolled_back"] == 1
    assert calls[0] == ("rollback", row.redis_counter_key, row.redis_token_key)
    assert calls[1][0:3] == ("finalize", row.reservation_key, "ROLLED_BACK")


@pytest.mark.asyncio
async def test_recovery_cleans_token_for_already_committed_ledger(monkeypatch):
    row = _reservation(state="COMMITTED", redis_reserved=True, redis_token_cleaned=False)
    session = _Session(rows=[row])
    calls = []

    def session_factory():
        return session

    async def delete_token(token_key):
        calls.append(("delete", token_key))
        return True

    async def mark_cleaned(key, owner):
        calls.append(("cleaned", key, owner))

    monkeypatch.setattr(recovery, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(recovery.RedisCapManager, "delete_reservation_token", delete_token)
    monkeypatch.setattr(recovery.CapReservationLedger, "mark_token_cleaned", mark_cleaned)

    stats = await recovery.recover_cap_reservations()

    assert stats["tokens_cleaned"] == 1
    assert calls[0] == ("delete", row.redis_token_key)
    assert calls[1] == ("cleaned", row.reservation_key, row.lease_owner)



@pytest.mark.asyncio
async def test_expired_daily_orphan_cleans_token_without_decrementing_missing_counter(monkeypatch):
    from datetime import date, datetime

    row = _reservation(state="RESERVED", redis_reserved=True)
    row.business_date = date(2026, 11, 8)
    sessions = [_Session(rows=[row]), _Session(event_id=None)]
    calls = []

    def session_factory():
        return sessions.pop(0)

    async def token_state(counter_key, token_key):
        return "UNKNOWN"  # token exists but its 48h daily counter key is gone

    async def counter_exists(counter_key):
        return False

    async def delete_token(token_key):
        calls.append(("delete", token_key))
        return True

    async def finalize(key, state, **kwargs):
        calls.append(("finalize", key, state, kwargs))

    monkeypatch.setattr(recovery, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(recovery, "get_app_now_naive", lambda: datetime(2026, 11, 11, 12, 0, 0))
    monkeypatch.setattr(recovery.RedisCapManager, "get_reservation_token_state", token_state)
    monkeypatch.setattr(recovery.RedisCapManager, "counter_key_exists", counter_exists)
    monkeypatch.setattr(recovery.RedisCapManager, "delete_reservation_token", delete_token)
    monkeypatch.setattr(recovery.CapReservationLedger, "finalize", finalize)

    stats = await recovery.recover_cap_reservations()

    assert stats["rolled_back"] == 1
    assert calls[0] == ("delete", row.redis_token_key)
    assert calls[1][0:3] == ("finalize", row.reservation_key, "ROLLED_BACK")


@pytest.mark.asyncio
async def test_expired_daily_absent_token_finalizes_without_redis_decrement(monkeypatch):
    from datetime import date, datetime

    row = _reservation(state="RESERVED", redis_reserved=True)
    row.business_date = date(2026, 11, 8)
    sessions = [_Session(rows=[row]), _Session(event_id=None)]
    calls = []

    def session_factory():
        return sessions.pop(0)

    async def token_state(counter_key, token_key):
        return "ABSENT"

    async def counter_exists(counter_key):
        return False

    async def finalize(key, state, **kwargs):
        calls.append((key, state, kwargs))

    async def forbidden_rollback(*args):
        raise AssertionError("expired daily counter must not be decremented")

    monkeypatch.setattr(recovery, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(recovery, "get_app_now_naive", lambda: datetime(2026, 11, 11, 12, 0, 0))
    monkeypatch.setattr(recovery.RedisCapManager, "get_reservation_token_state", token_state)
    monkeypatch.setattr(recovery.RedisCapManager, "counter_key_exists", counter_exists)
    monkeypatch.setattr(recovery.RedisCapManager, "rollback_reservation_keys", forbidden_rollback)
    monkeypatch.setattr(recovery.CapReservationLedger, "finalize", finalize)

    stats = await recovery.recover_cap_reservations()

    assert stats["rolled_back"] == 1
    assert calls[0][0:2] == (row.reservation_key, "ROLLED_BACK")



@pytest.mark.asyncio
async def test_recovery_status_reports_backlog_and_oldest_pending_age(monkeypatch):
    from datetime import datetime

    class StatusResult:
        def all(self):
            return [
                ("PREPARED", 3),
                ("RESERVED", 4),
                ("NEEDS_RECONCILIATION", 1),
            ]

    class StatusSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, statement):
            return StatusResult()

        async def scalar(self, statement):
            if not hasattr(self, "scalar_calls"):
                self.scalar_calls = 0
            self.scalar_calls += 1
            return [
                datetime(2026, 11, 11, 11, 50, 0),
                2,
            ][self.scalar_calls - 1]

    monkeypatch.setattr(recovery, "AsyncSessionLocal", StatusSession)
    monkeypatch.setattr(
        recovery, "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )

    status = await recovery.get_cap_reservation_recovery_status()

    assert status == {
        "pending_prepared": 3,
        "pending_reserved": 4,
        "needs_reconciliation": 1,
        "committed_token_cleanup_pending": 2,
        "oldest_pending_seconds": 600,
    }


@pytest.mark.asyncio
async def test_absent_token_with_existing_counter_requires_reconciliation(monkeypatch):
    """token 可能被独立淘汰；counter 仍在时不能把 ABSENT 当成未预留。"""
    row = _reservation(state="PREPARED", redis_reserved=False)
    sessions = [_Session(rows=[row]), _Session(event_id=None)]
    calls = []

    def session_factory():
        return sessions.pop(0)

    async def token_state(counter_key, token_key):
        return "ABSENT"

    async def counter_exists(counter_key):
        return True

    async def mark_needs(key, error, **kwargs):
        calls.append((key, error, kwargs))

    async def forbidden_finalize(*args, **kwargs):
        raise AssertionError("counter exists: ABSENT token must not finalize as rolled back")

    monkeypatch.setattr(recovery, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(recovery.RedisCapManager, "get_reservation_token_state", token_state)
    monkeypatch.setattr(recovery.RedisCapManager, "counter_key_exists", counter_exists)
    monkeypatch.setattr(recovery.CapReservationLedger, "mark_needs_reconciliation", mark_needs)
    monkeypatch.setattr(recovery.CapReservationLedger, "finalize", forbidden_finalize)

    stats = await recovery.recover_cap_reservations()

    assert stats["needs_reconciliation"] == 1
    assert calls[0][0] == row.reservation_key
    assert "token ABSENT" in calls[0][1]
    assert "counter still exists" in calls[0][1]
