from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql

import app.scheduler_module.lock as scheduler_lock
import app.scheduler_module.scheduler as scheduler


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeSession:
    def __init__(self, *, db_now=None, row=None):
        self.db_now = db_now
        self.row = row
        self.executed = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def execute(self, statement):
        self.executed.append(statement)
        return _ScalarResult(self.row)

    async def scalar(self, statement):
        self.executed.append(statement)
        return self.db_now

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def close(self):
        self.closed = True


def _task_record(*, db_now: datetime, elapsed_seconds: int):
    return SimpleNamespace(
        task_name="clock-test",
        is_active=True,
        is_running=True,
        last_run_time=db_now - timedelta(seconds=elapsed_seconds),
        last_run_pid=111,
        last_run_host="previous-host",
        run_count=4,
        success_count=0,
        error_count=0,
        last_error=None,
        updated_at=None,
        last_finish_time=None,
        cron_expression=None,
    )


@pytest.mark.asyncio
async def test_acquire_task_lock_uses_database_time_not_fast_worker_clock(monkeypatch):
    db_now = datetime(2026, 11, 21, 12, 0, 0)
    record = _task_record(db_now=db_now, elapsed_seconds=100)
    db = _FakeSession(db_now=db_now)

    monkeypatch.setattr(scheduler_lock, "AsyncSessionLocal", lambda: db)

    async def load_record(_db, _task_name):
        return record

    monkeypatch.setattr(scheduler_lock, "_load_or_create_task_record", load_record)
    monkeypatch.setattr(
        scheduler_lock,
        "get_app_now_naive",
        lambda: db_now + timedelta(days=1),
    )

    acquired, session = await scheduler_lock.acquire_task_lock(
        "clock-test", timeout_seconds=300
    )

    assert acquired is False
    assert session is None
    assert record.last_run_pid == 111
    assert record.run_count == 4
    assert db.rolled_back is True
    assert db.closed is True
    assert any(
        "UTC_TIMESTAMP" in str(statement.compile(dialect=mysql.dialect())).upper()
        for statement in db.executed
    )


@pytest.mark.asyncio
async def test_acquire_task_lock_recovers_stale_row_using_database_time(monkeypatch):
    db_now = datetime(2026, 11, 21, 12, 0, 0)
    record = _task_record(db_now=db_now, elapsed_seconds=400)
    db = _FakeSession(db_now=db_now)

    monkeypatch.setattr(scheduler_lock, "AsyncSessionLocal", lambda: db)

    async def load_record(_db, _task_name):
        return record

    monkeypatch.setattr(scheduler_lock, "_load_or_create_task_record", load_record)
    monkeypatch.setattr(
        scheduler_lock,
        "get_app_now_naive",
        lambda: db_now - timedelta(days=1),
    )

    acquired, session = await scheduler_lock.acquire_task_lock(
        "clock-test", timeout_seconds=300
    )

    assert acquired is True
    assert session is db
    assert record.is_running is True
    assert record.last_run_time == db_now
    assert record.run_count == 5
    assert db.committed is True
    assert db.closed is False


@pytest.mark.asyncio
async def test_release_task_lock_relocks_row_before_owner_check(monkeypatch):
    now = datetime(2026, 11, 21, 12, 0, 0)
    record = SimpleNamespace(
        last_run_pid=222,
        last_run_host="scheduler-host",
        is_running=True,
        updated_at=None,
        last_finish_time=None,
        success_count=2,
        error_count=0,
        last_error=None,
        run_count=3,
    )
    db = _FakeSession(row=record)
    monkeypatch.setattr(scheduler_lock, "get_current_pid", lambda: 222)
    monkeypatch.setattr(scheduler_lock, "CURRENT_HOST", "scheduler-host")
    monkeypatch.setattr(scheduler_lock, "get_app_now_naive", lambda: now)

    await scheduler_lock.release_task_lock(
        db, "clock-test", success=True, result_message="done"
    )

    compiled = str(db.executed[0].compile(dialect=mysql.dialect())).upper()
    assert "FOR UPDATE" in compiled
    assert db.executed[0].get_execution_options()["populate_existing"] is True
    assert record.is_running is False
    assert record.success_count == 3
    assert record.last_error == "done"
    assert db.committed is True


@pytest.mark.asyncio
async def test_scheduler_stale_precheck_uses_database_clock(monkeypatch):
    db_now = datetime(2026, 11, 21, 12, 0, 0)
    record = _task_record(db_now=db_now, elapsed_seconds=400)
    db = _FakeSession(db_now=db_now, row=record)
    queued = {}

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(scheduler, "is_scheduler_shutting_down", lambda: False)
    monkeypatch.setattr(scheduler, "_task_lock_timeout_seconds", lambda _name: 300)
    monkeypatch.setattr(
        scheduler,
        "get_app_now_naive",
        lambda: db_now - timedelta(days=1),
    )

    async def submit_task_to_queue(**kwargs):
        queued.update(kwargs)

    monkeypatch.setattr(scheduler, "submit_task_to_queue", submit_task_to_queue)

    await scheduler.execute_task_with_lock("clock-test", lambda: None)

    assert "task_func" in queued
    assert db.closed is True
    assert any(
        "UTC_TIMESTAMP" in str(statement.compile(dialect=mysql.dialect())).upper()
        for statement in db.executed
    )
