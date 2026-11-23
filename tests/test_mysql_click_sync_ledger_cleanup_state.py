"""真实 MySQL 8 集成测试：点击刷盘账本清理状态必须跨事务持久化。"""
from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import short_link_click_counter as counter
from app.models.postback import (
    ShortLinkClickSyncBatch,
    ShortLinkClickSyncLedgerMaintenanceState,
)


HOST = os.getenv("MYSQL_INTEGRATION_HOST")
DATABASE = os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci")
_DESTRUCTIVE_TESTS_ENABLED = os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip()).is_loopback
    except ValueError:
        return False


_SAFE_MYSQL_CI = (
    os.getenv("UNIT_TEST") == "1"
    and os.getenv("GITHUB_ACTIONS") == "true"
    and _DESTRUCTIVE_TESTS_ENABLED
    and _is_loopback_host(HOST)
    and DATABASE == "platform_ci"
)

if (
    os.getenv("GITHUB_ACTIONS") == "true"
    or (os.getenv("UNIT_TEST") == "1" and HOST)
) and not _SAFE_MYSQL_CI:
    raise RuntimeError(
        "拒绝执行点击刷盘账本清理状态 MySQL 测试：必须使用 loopback 主机、platform_ci 数据库，"
        "并显式设置 MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS=1"
    )

pytestmark = pytest.mark.skipif(
    not _SAFE_MYSQL_CI,
    reason="仅在 GitHub Actions 本机隔离 MySQL 8 服务中运行",
)


def _engine():
    url = URL.create(
        "mysql+aiomysql",
        username=os.getenv("MYSQL_INTEGRATION_USER", "root"),
        password=os.getenv("MYSQL_INTEGRATION_PASSWORD", ""),
        host=HOST,
        port=int(os.getenv("MYSQL_INTEGRATION_PORT", "3306")),
        database=DATABASE,
        query={"charset": "utf8mb4"},
    )
    return create_async_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=0)


async def _reset_tables(engine, batches):
    async with engine.begin() as connection:
        await connection.run_sync(
            ShortLinkClickSyncLedgerMaintenanceState.__table__.drop,
            checkfirst=True,
        )
        await connection.run_sync(ShortLinkClickSyncBatch.__table__.drop, checkfirst=True)
        await connection.run_sync(ShortLinkClickSyncBatch.__table__.create)
        await connection.run_sync(ShortLinkClickLedgerMaintenanceState.__table__.create)
        if batches:
            await connection.execute(ShortLinkClickSyncBatch.__table__.insert(), batches)


async def _drop_tables(engine):
    async with engine.begin() as connection:
        await connection.run_sync(
            ShortLinkClickSyncLedgerMaintenanceState.__table__.drop,
            checkfirst=True,
        )
        await connection.run_sync(ShortLinkClickSyncBatch.__table__.drop, checkfirst=True)


@pytest.mark.asyncio
async def test_mysql_redis_unknown_persists_degraded_state_without_ack(monkeypatch):
    engine = _engine()
    now = datetime(2026, 11, 23, 12, 0, 0)
    monkeypatch.setattr(counter, "get_app_now_naive", lambda: now)

    class BrokenRedis:
        async def exists(self, _key):
            raise ConnectionError("redis://svc:secret@cache.internal/0")

    try:
        await _reset_tables(engine, [{
            "batch_id": "batch-redis-fail",
            "short_code": "short-a",
            "click_count": 7,
            "created_at": now - timedelta(minutes=5),
            "acknowledged_at": None,
        }])
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            result = await counter._cleanup_click_sync_batch_ledger(db, BrokenRedis())

        assert result["status"] == "degraded"
        assert result["redis_check_failures"] == 1
        assert result["acknowledged_count"] == 0

        async with engine.connect() as connection:
            state = (
                await connection.execute(
                    select(ShortLinkClickSyncLedgerMaintenanceState)
                    .where(ShortLinkClickSyncLedgerMaintenanceState.id == 1)
                )
            ).scalar_one()
            acknowledged_at = await connection.scalar(
                text(
                    "SELECT acknowledged_at FROM short_link_click_sync_batches "
                    "WHERE batch_id='batch-redis-fail'"
                )
            )
        assert state.status == "degraded"
        assert state.consecutive_failure_count == 1
        assert state.total_failure_count == 1
        assert state.last_failure_at == now
        assert state.last_error_type == "redis_exists:ConnectionError"
        assert acknowledged_at is None
    finally:
        await _drop_tables(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_success_resets_consecutive_failures_and_preserves_last_failure(monkeypatch):
    engine = _engine()
    now = datetime(2026, 11, 23, 12, 0, 0)
    previous_failure = now - timedelta(minutes=20)
    monkeypatch.setattr(counter, "get_app_now_naive", lambda: now)

    class Redis:
        async def exists(self, _key):
            return 0

    async def invalidate(_short_code):
        return True

    monkeypatch.setattr(counter, "invalidate_short_link_cache", invalidate)
    try:
        await _reset_tables(engine, [
            {
                "batch_id": "batch-to-ack",
                "short_code": "short-a",
                "click_count": 3,
                "created_at": now - timedelta(minutes=5),
                "acknowledged_at": None,
            },
            {
                "batch_id": "old-acked",
                "short_code": "short-b",
                "click_count": 1,
                "created_at": now - timedelta(days=60),
                "acknowledged_at": now - timedelta(days=40),
            },
        ])
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            db.add(
                ShortLinkClickSyncLedgerMaintenanceState(
                    id=1,
                    status="degraded",
                    consecutive_failure_count=3,
                    total_failure_count=9,
                    last_failure_at=previous_failure,
                    last_error_type="redis_exists:ConnectionError",
                )
            )
            await db.commit()

        async with factory() as db:
            result = await counter._cleanup_click_sync_batch_ledger(db, Redis())

        assert result["status"] == "healthy"
        assert result["acknowledged_count"] == 1
        assert result["deleted_count"] == 1

        async with factory() as db:
            state = await db.get(ShortLinkClickSyncLedgerMaintenanceState, 1)
            pending_ack = await db.scalar(
                select(ShortLinkClickSyncBatch.acknowledged_at)
                .where(ShortLinkClickSyncBatch.batch_id == "batch-to-ack")
            )
            old_row = await db.get(ShortLinkClickSyncBatch, "old-acked")
        assert state.status == "healthy"
        assert state.consecutive_failure_count == 0
        assert state.total_failure_count == 9
        assert state.last_failure_at == previous_failure
        assert state.last_success_at == now
        assert state.last_error_type is None
        assert pending_ack == now
        assert old_row is None
    finally:
        await _drop_tables(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_db_commit_failure_persists_failed_state_in_separate_session(monkeypatch):
    engine = _engine()
    now = datetime(2026, 11, 23, 12, 0, 0)
    monkeypatch.setattr(counter, "get_app_now_naive", lambda: now)

    class FailCommitSession(AsyncSession):
        async def commit(self):
            raise RuntimeError("mysql://svc:secret@db.internal SELECT * FROM credentials")

    try:
        await _reset_tables(engine, [])
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        failing_factory = async_sessionmaker(
            engine, class_=FailCommitSession, expire_on_commit=False
        )
        monkeypatch.setattr(counter, "AsyncSessionLocal", factory)

        async with failing_factory() as db:
            result = await counter._cleanup_click_sync_batch_ledger(db, object())

        assert result["status"] == "failed"
        assert result["error_type"] == "RuntimeError"
        assert result["failure_state_persisted"] is True

        async with factory() as db:
            state = await db.get(ShortLinkClickSyncLedgerMaintenanceState, 1)
        assert state.status == "failed"
        assert state.consecutive_failure_count == 1
        assert state.total_failure_count == 1
        assert state.last_failure_at == now
        assert state.last_error_type == "RuntimeError"
    finally:
        await _drop_tables(engine)
        await engine.dispose()
