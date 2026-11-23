"""敏感路径探测日志分批清理逻辑测试；MySQL 锁与执行计划由独立集成测试验证。"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.security import SensitivePathProbeLog
from app.scheduler_module.tasks import cleanup_sensitive_path_probes as cleanup


@pytest.fixture
def fixed_now(monkeypatch):
    now = datetime(2026, 11, 23, 12, 0, 0)
    monkeypatch.setattr(cleanup, "get_app_now_naive", lambda: now)
    return now


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SensitivePathProbeLog.__table__.create)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def _insert_rows(factory, rows):
    async with factory() as db:
        db.add_all(rows)
        await db.commit()


@pytest.mark.asyncio
async def test_cleanup_uses_stable_cutoff_and_bounded_batches(fixed_now):
    engine, factory = await _make_db()
    cutoff = fixed_now - timedelta(days=30)
    try:
        await _insert_rows(factory, [
            SensitivePathProbeLog(request_path=f"/old/{i}", created_at=cutoff - timedelta(seconds=1))
            for i in range(5)
        ] + [
            SensitivePathProbeLog(request_path="/boundary", created_at=cutoff),
            SensitivePathProbeLog(request_path="/new", created_at=cutoff + timedelta(seconds=1)),
        ])

        async with factory() as db:
            result = await cleanup.cleanup_sensitive_path_probe_logs(
                retention_days=30, db=db, batch_size=2, max_batches=10, max_runtime_seconds=20
            )

        assert result["deleted_count"] == 5
        assert result["batch_count"] == 3
        assert result["complete"] is True
        assert result["remaining_possible"] is False
        assert result["cutoff"] == cutoff.strftime("%Y-%m-%d %H:%M:%S")

        async with factory() as db:
            remaining = list((await db.execute(
                select(SensitivePathProbeLog.request_path).order_by(SensitivePathProbeLog.id)
            )).scalars())
        assert remaining == ["/boundary", "/new"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_budget_returns_partial_instead_of_false_success(fixed_now):
    engine, factory = await _make_db()
    cutoff = fixed_now - timedelta(days=30)
    try:
        await _insert_rows(factory, [
            SensitivePathProbeLog(request_path=f"/old/{i}", created_at=cutoff - timedelta(days=1))
            for i in range(5)
        ])
        async with factory() as db:
            result = await cleanup.cleanup_sensitive_path_probe_logs(
                retention_days=30, db=db, batch_size=2, max_batches=1, max_runtime_seconds=20
            )
        assert result["deleted_count"] == 2
        assert result["batch_count"] == 1
        assert result["complete"] is False
        assert result["remaining_possible"] is True
        assert "未完成" in result["message"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failed_batch_preserves_committed_progress_and_redacts_error(fixed_now):
    engine, factory = await _make_db()
    cutoff = fixed_now - timedelta(days=30)

    class FailSecondCommitSession(AsyncSession):
        commits = 0

        async def commit(self):
            self.commits += 1
            if self.commits == 2:
                raise RuntimeError("mysql://svc:secret@db.internal SELECT * FROM sensitive_data")
            await super().commit()

    failing_factory = async_sessionmaker(
        engine, class_=FailSecondCommitSession, expire_on_commit=False
    )
    try:
        await _insert_rows(factory, [
            SensitivePathProbeLog(request_path=f"/old/{i}", created_at=cutoff - timedelta(days=1))
            for i in range(5)
        ])
        async with failing_factory() as db:
            with pytest.raises(cleanup.SensitivePathProbeCleanupError) as captured:
                await cleanup.cleanup_sensitive_path_probe_logs(
                    retention_days=30, db=db, batch_size=2, max_batches=10, max_runtime_seconds=20
                )

        error = captured.value
        assert error.deleted_count == 2
        assert error.batch_count == 1
        assert error.complete is False
        assert error.remaining_possible is True
        assert "secret" not in str(error)
        assert "SELECT" not in str(error)

        async with factory() as db:
            rows = list((await db.execute(select(SensitivePathProbeLog.id))).scalars())
        assert len(rows) == 3
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"retention_days": 0},
        {"retention_days": -1},
        {"retention_days": True},
        {"retention_days": 30, "batch_size": 0},
        {"retention_days": 30, "batch_size": 5001},
        {"retention_days": 30, "max_batches": 1001},
        {"retention_days": 30, "max_runtime_seconds": 301},
    ],
)
@pytest.mark.asyncio
async def test_cleanup_rejects_invalid_budget_configuration(kwargs):
    with pytest.raises(ValueError):
        await cleanup.cleanup_sensitive_path_probe_logs(**kwargs)


@pytest.mark.asyncio
async def test_cleanup_timeout_reports_unknown_batch_without_false_success(monkeypatch, fixed_now):
    import asyncio

    class TimeoutDB:
        async def execute(self, _statement):
            raise AssertionError("wait_for timeout should occur before database execution")

        rollback = AsyncMock()
        close = AsyncMock()

    async def timeout_immediately(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(cleanup.asyncio, "wait_for", timeout_immediately)
    db = TimeoutDB()
    with pytest.raises(cleanup.SensitivePathProbeCleanupError) as captured:
        await cleanup.cleanup_sensitive_path_probe_logs(
            retention_days=30, db=db, batch_size=10, max_batches=10, max_runtime_seconds=1
        )
    assert captured.value.error_type == "TimeoutError"
    assert captured.value.complete is False
    assert captured.value.remaining_possible is True
    assert captured.value.deleted_count == 0
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_empty_table_is_complete(fixed_now):
    engine, factory = await _make_db()
    try:
        async with factory() as db:
            result = await cleanup.cleanup_sensitive_path_probe_logs(
                retention_days=30, db=db, batch_size=10, max_batches=2, max_runtime_seconds=5
            )
        assert result["deleted_count"] == 0
        assert result["batch_count"] == 0
        assert result["complete"] is True
        assert result["remaining_possible"] is False
    finally:
        await engine.dispose()
