"""只读 schema revision gate 测试；不执行 DDL 变更或外部服务调用。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrations.gate import SchemaRevisionNotReady, verify_schema_revision
from app.db.migrations.manifest import Migration


def _migrations(tmp_path: Path):
    result = []
    for revision in ("20261110_gate_first", "20261111_gate_second"):
        relative = f"sql/migrations/{revision}.sql"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"-- {revision}\n", encoding="utf-8")
        result.append(
            Migration(
                revision=revision,
                path=relative,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return tuple(result)


async def _create_ledger(connection):
    await connection.execute(
        text(
            "CREATE TABLE platform_schema_migrations ("
            "revision VARCHAR(64) NOT NULL PRIMARY KEY, "
            "checksum CHAR(64) NOT NULL, status VARCHAR(16) NOT NULL, "
            "execution_order INTEGER NOT NULL)"
        )
    )


@pytest.mark.asyncio
async def test_schema_gate_accepts_current_applied_history(tmp_path: Path):
    migrations = _migrations(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await _create_ledger(connection)
            for order, migration in enumerate(migrations, start=1):
                await connection.execute(
                    text(
                        "INSERT INTO platform_schema_migrations "
                        "(revision, checksum, status, execution_order) "
                        "VALUES (:revision, :checksum, 'applied', :order)"
                    ),
                    {
                        "revision": migration.revision,
                        "checksum": migration.sha256,
                        "order": order,
                    },
                )
            current = await verify_schema_revision(
                connection, repository_root=tmp_path, migrations=migrations
            )
        assert current == migrations[-1].revision
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_schema_gate_rejects_missing_ledger_without_creating_it(tmp_path: Path):
    migrations = _migrations(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.connect() as connection:
            with pytest.raises(SchemaRevisionNotReady, match="ledger 缺失"):
                await verify_schema_revision(
                    connection, repository_root=tmp_path, migrations=migrations
                )
            tables = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type='table' AND name='platform_schema_migrations'"
                )
            )
            assert tables == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_schema_gate_rejects_pending_migration(tmp_path: Path):
    migrations = _migrations(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await _create_ledger(connection)
            await connection.execute(
                text(
                    "INSERT INTO platform_schema_migrations "
                    "(revision, checksum, status, execution_order) "
                    "VALUES (:revision, :checksum, 'applied', 1)"
                ),
                {
                    "revision": migrations[0].revision,
                    "checksum": migrations[0].sha256,
                },
            )
            with pytest.raises(SchemaRevisionNotReady, match="schema revision 落后"):
                await verify_schema_revision(
                    connection, repository_root=tmp_path, migrations=migrations
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_schema_gate_rejects_failed_or_running_migration(tmp_path: Path):
    migrations = _migrations(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await _create_ledger(connection)
            await connection.execute(
                text(
                    "INSERT INTO platform_schema_migrations "
                    "(revision, checksum, status, execution_order) "
                    "VALUES (:revision, :checksum, 'running', 1)"
                ),
                {
                    "revision": migrations[0].revision,
                    "checksum": migrations[0].sha256,
                },
            )
            with pytest.raises(SchemaRevisionNotReady, match="未完成 migration"):
                await verify_schema_revision(
                    connection, repository_root=tmp_path, migrations=migrations
                )
    finally:
        await engine.dispose()
