"""点击刷盘账本清理独立状态的逻辑与脱敏回归测试。"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core import short_link_click_counter as counter


class _Scalars:
    def __init__(self, values=()):
        self.values = list(values)

    def all(self):
        return self.values


class _Result:
    def __init__(self, *, rows=(), scalar=None, rowcount=0):
        self.rows = list(rows)
        self.scalar = scalar
        self.rowcount = rowcount

    def fetchall(self):
        return self.rows

    def scalars(self):
        return _Scalars(self.rows)

    def scalar_one_or_none(self):
        return self.scalar


class _MemoryDB:
    def __init__(self, *, unacked_rows=(), state=None):
        self.unacked_rows = list(unacked_rows)
        self.state = state
        self.statements = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _Result(rows=self.unacked_rows)
        if "short_link_click_sync_ledger_maintenance" in str(statement):
            return _Result(scalar=self.state)
        return _Result(rows=(), rowcount=1)

    def add(self, state):
        self.state = state

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_redis_state_unknown_is_persisted_as_degraded_without_ack(monkeypatch):
    fixed_now = datetime(2026, 11, 23, 12, 0, 0)
    monkeypatch.setattr(counter, "get_app_now_naive", lambda: fixed_now)

    class BrokenRedis:
        async def exists(self, _key):
            raise RuntimeError("redis://svc:secret@cache.internal/0")

    db = _MemoryDB(unacked_rows=[("batch-1", "short-1")])
    result = await counter._cleanup_click_sync_batch_ledger(db, BrokenRedis())

    assert result["status"] == "degraded"
    assert result["redis_check_failures"] == 1
    assert result["acknowledged_count"] == 0
    assert db.committed is True
    assert db.rolled_back is False
    assert db.state.status == "degraded"
    assert db.state.consecutive_failure_count == 1
    assert db.state.total_failure_count == 1
    assert db.state.last_failure_at == fixed_now
    assert db.state.last_error_type == "redis_exists:RuntimeError"
    assert "secret" not in db.state.last_error_type


@pytest.mark.asyncio
async def test_success_resets_consecutive_failures_but_preserves_last_failure(monkeypatch):
    fixed_now = datetime(2026, 11, 23, 12, 0, 0)
    previous_failure = fixed_now - timedelta(minutes=10)
    monkeypatch.setattr(counter, "get_app_now_naive", lambda: fixed_now)
    state = SimpleNamespace(
        id=1,
        status="degraded",
        consecutive_failure_count=4,
        total_failure_count=8,
        last_attempt_at=previous_failure,
        last_success_at=None,
        last_failure_at=previous_failure,
        last_error_type="redis_exists:ConnectionError",
        last_unacked_scanned_count=1,
        last_acknowledged_count=0,
        last_deleted_count=0,
        last_redis_check_failures=1,
        last_cache_invalidation_failures=0,
    )

    class Redis:
        async def exists(self, _key):
            return 1

    db = _MemoryDB(unacked_rows=[], state=state)
    result = await counter._cleanup_click_sync_batch_ledger(db, Redis())

    assert result["status"] == "healthy"
    assert db.state.status == "healthy"
    assert db.state.consecutive_failure_count == 0
    assert db.state.total_failure_count == 8
    assert db.state.last_failure_at == previous_failure
    assert db.state.last_success_at == fixed_now
    assert db.state.last_error_type is None
