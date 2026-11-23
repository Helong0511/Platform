"""真实 MySQL 8 集成测试：验证敏感路径日志分批事务、边界与索引计划。"""
from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.security import SensitivePathProbeLog
from app.scheduler_module.tasks import cleanup_sensitive_path_probes as cleanup


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
        "拒绝执行敏感路径日志 MySQL 集成测试：必须使用 loopback 主机、platform_ci 数据库，"
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


async def _reset_table(engine, rows):
    async with engine.begin() as connection:
        await connection.run_sync(SensitivePathProbeLog.__table__.drop, checkfirst=True)
        await connection.run_sync(SensitivePathProbeLog.__table__.create)
        if rows:
            await connection.execute(
                SensitivePathProbeLog.__table__.insert(),
                rows,
            )


async def _drop_table(engine):
    async with engine.begin() as connection:
        await connection.run_sync(SensitivePathProbeLog.__table__.drop, checkfirst=True)


def _rows(now: datetime, old_count: int, recent_count: int):
    cutoff = now - timedelta(days=30)
    return [
        {
            "request_path": f"/old/{index}",
            "created_at": cutoff - timedelta(seconds=1),
        }
        for index in range(old_count)
    ] + [
        {
            "request_path": f"/recent/{index}",
            "created_at": cutoff + timedelta(seconds=1),
        }
        for index in range(recent_count)
    ]


@pytest.mark.asyncio
async def test_mysql_cleanup_batches_and_uses_created_at_index(monkeypatch):
    engine = _engine()
    now = datetime(2026, 11, 23, 12, 0, 0)
    monkeypatch.setattr(cleanup, "get_app_now_naive", lambda: now)
    try:
        await _reset_table(engine, _rows(now, old_count=300, recent_count=5700))
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with engine.connect() as connection:
            plan = (
                await connection.execute(
                    text(
                        "EXPLAIN SELECT id FROM sensitive_path_probe_logs "
                        "WHERE created_at < :cutoff ORDER BY id ASC LIMIT 100"
                    ),
                    {"cutoff": now - timedelta(days=30)},
                )
            ).mappings().all()
        selected_keys = {row.get("key") for row in plan}
        assert "idx_sensitive_probe_created_at" in selected_keys, plan

        async with factory() as db:
            result = await cleanup.cleanup_sensitive_path_probe_logs(
                retention_days=30,
                db=db,
                batch_size=100,
                max_batches=1,
                max_runtime_seconds=20,
            )

        assert result["deleted_count"] == 100
        assert result["batch_count"] == 1
        assert result["complete"] is False
        assert result["remaining_possible"] is True

        async with engine.connect() as connection:
            old_remaining = await connection.scalar(
                text("SELECT COUNT(*) FROM sensitive_path_probe_logs WHERE created_at < :cutoff"),
                {"cutoff": now - timedelta(days=30)},
            )
            recent_remaining = await connection.scalar(
                text("SELECT COUNT(*) FROM sensitive_path_probe_logs WHERE created_at >= :cutoff"),
                {"cutoff": now - timedelta(days=30)},
            )
        assert old_remaining == 200
        assert recent_remaining == 5700
    finally:
        await _drop_table(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_failed_second_batch_keeps_first_commit(monkeypatch):
    engine = _engine()
    now = datetime(2026, 11, 23, 12, 0, 0)
    monkeypatch.setattr(cleanup, "get_app_now_naive", lambda: now)

    class FailSecondCommitSession(AsyncSession):
        commit_count = 0

        async def commit(self):
            self.commit_count += 1
            if self.commit_count == 2:
                raise RuntimeError("mysql://svc:secret@internal SELECT * FROM credentials")
            await super().commit()

    try:
        await _reset_table(engine, _rows(now, old_count=55, recent_count=10))
        factory = async_sessionmaker(
            engine, class_=FailSecondCommitSession, expire_on_commit=False
        )
        async with factory() as db:
            with pytest.raises(cleanup.SensitivePathProbeCleanupError) as captured:
                await cleanup.cleanup_sensitive_path_probe_logs(
                    retention_days=30,
                    db=db,
                    batch_size=20,
                    max_batches=10,
                    max_runtime_seconds=20,
                )

        assert captured.value.deleted_count == 20
        assert captured.value.batch_count == 1
        assert "secret" not in str(captured.value)

        async with engine.connect() as connection:
            old_remaining = await connection.scalar(
                text("SELECT COUNT(*) FROM sensitive_path_probe_logs WHERE created_at < :cutoff"),
                {"cutoff": now - timedelta(days=30)},
            )
        assert old_remaining == 35
    finally:
        await _drop_table(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_insert_between_batches_does_not_expand_fixed_cutoff(monkeypatch):
    engine = _engine()
    now = datetime(2026, 11, 23, 12, 0, 0)
    cutoff = now - timedelta(days=30)
    monkeypatch.setattr(cleanup, "get_app_now_naive", lambda: now)
    plain_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    class InsertAfterFirstCommitSession(AsyncSession):
        commit_count = 0

        async def commit(self):
            await super().commit()
            self.commit_count += 1
            if self.commit_count == 1:
                # 模拟另一请求在批次之间写入一条新日志；它必须留在 cutoff 之后。
                async with plain_factory() as writer:
                    writer.add(
                        SensitivePathProbeLog(
                            request_path="/inserted-between-batches",
                            created_at=now,
                        )
                    )
                    await writer.commit()

    try:
        await _reset_table(engine, [
            {
                "request_path": f"/old/{index}",
                "created_at": cutoff - timedelta(seconds=1),
            }
            for index in range(2)
        ])
        factory = async_sessionmaker(
            engine, class_=InsertAfterFirstCommitSession, expire_on_commit=False
        )
        async with factory() as db:
            result = await cleanup.cleanup_sensitive_path_probe_logs(
                retention_days=30,
                db=db,
                batch_size=1,
                max_batches=10,
                max_runtime_seconds=20,
            )

        assert result["deleted_count"] == 2
        assert result["complete"] is True
        async with engine.connect() as connection:
            paths = (
                await connection.execute(
                    text("SELECT request_path FROM sensitive_path_probe_logs")
                )
            ).scalars().all()
        assert paths == ["/inserted-between-batches"]
    finally:
        await _drop_table(engine)
        await engine.dispose()
