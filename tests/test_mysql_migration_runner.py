"""独立 Migration Runner 的真实 MySQL 隔离集成测试。

只允许 GitHub Actions loopback 临时 MySQL；数据库名随机生成并在 finally 中删除。
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import secrets
from pathlib import Path

import pytest
import pymysql
from sqlalchemy import URL

from app.db.migrations.ledger import MigrationLedgerError
from app.db.migrations.manifest import Migration
from app.db.migrations.runner import (
    MigrationExecutionError,
    MigrationLockUnavailable,
    MigrationRunnerError,
    _migration_lock_name,
    apply_migrations,
)


HOST = os.getenv("MYSQL_INTEGRATION_HOST")
PORT = int(os.getenv("MYSQL_INTEGRATION_PORT", "3306"))
ROOT_USER = os.getenv("MYSQL_INTEGRATION_USER", "root")
ROOT_PASSWORD = os.getenv("MYSQL_INTEGRATION_PASSWORD", "")


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
    and os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _is_loopback_host(HOST)
    and os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci") == "platform_ci"
)
if (
    os.getenv("GITHUB_ACTIONS") == "true"
    or (os.getenv("UNIT_TEST") == "1" and HOST)
) and not _SAFE_MYSQL_CI:
    raise RuntimeError(
        "拒绝运行 Migration Runner 集成测试：必须使用 GitHub Actions loopback 临时 MySQL"
    )

pytestmark = pytest.mark.skipif(
    not _SAFE_MYSQL_CI,
    reason="仅在 GitHub Actions loopback 临时 MySQL 中运行",
)


def _root_connect(database: str | None = None):
    return pymysql.connect(
        host=HOST,
        port=PORT,
        user=ROOT_USER,
        password=ROOT_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )


def _create_database() -> str:
    database = f"platform_ci_mr_{secrets.token_hex(5)}"
    connection = _root_connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
    finally:
        connection.close()
    return database


def _drop_database(database: str) -> None:
    connection = _root_connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


def _database_url(database: str) -> str:
    return URL.create(
        "mysql+aiomysql",
        username=ROOT_USER,
        password=ROOT_PASSWORD,
        host=HOST,
        port=PORT,
        database=database,
        query={"charset": "utf8mb4"},
    ).render_as_string(hide_password=False)


def _write_migrations(tmp_path: Path, definitions):
    migrations = []
    for revision, sql in definitions:
        relative = f"sql/migrations/{revision}.sql"
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sql, encoding="utf-8")
        migrations.append(
            Migration(
                revision=revision,
                path=relative,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            )
        )
    return tuple(migrations)


@pytest.mark.asyncio
async def test_runner_applies_in_order_and_is_idempotent(tmp_path: Path):
    database = _create_database()
    try:
        migrations = _write_migrations(
            tmp_path,
            [
                (
                    "20261110_runner_create",
                    "CREATE TABLE runner_probe ("
                    "id INT NOT NULL PRIMARY KEY, value VARCHAR(32) NOT NULL"
                    ") ENGINE=InnoDB;",
                ),
                (
                    "20261111_runner_alter",
                    "ALTER TABLE runner_probe "
                    "ADD COLUMN enabled TINYINT NOT NULL DEFAULT 1;",
                ),
            ],
        )
        url = _database_url(database)

        applied = await apply_migrations(
            url, repository_root=tmp_path, migrations=migrations
        )
        assert applied == tuple(item.revision for item in migrations)

        # 第二次执行必须只读 ledger 并返回空计划，不重复执行 DDL。
        assert await apply_migrations(
            url, repository_root=tmp_path, migrations=migrations
        ) == ()

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SHOW COLUMNS FROM runner_probe")
                columns = {row[0] for row in cursor.fetchall()}
                assert columns == {"id", "value", "enabled"}
                cursor.execute(
                    "SELECT revision, status, execution_order "
                    "FROM platform_schema_migrations ORDER BY execution_order"
                )
                rows = cursor.fetchall()
                assert rows == (
                    (migrations[0].revision, "applied", 1),
                    (migrations[1].revision, "applied", 2),
                )
    finally:
        _drop_database(database)


@pytest.mark.asyncio
async def test_runner_requires_exclusive_same_database_get_lock(tmp_path: Path):
    database = _create_database()
    lock_connection = _root_connect(database)
    try:
        migrations = _write_migrations(
            tmp_path,
            [("20261110_runner_lock", "CREATE TABLE lock_probe (id INT PRIMARY KEY);")],
        )
        lock_name = _migration_lock_name(database)
        with lock_connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0)", (lock_name,))
            assert cursor.fetchone()[0] == 1

        with pytest.raises(MigrationLockUnavailable):
            await apply_migrations(
                _database_url(database),
                repository_root=tmp_path,
                migrations=migrations,
                lock_timeout=0,
            )

        with lock_connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'platform_schema_migrations'",
                (database,),
            )
            assert cursor.fetchone()[0] == 0
    finally:
        try:
            with lock_connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (_migration_lock_name(database),))
        finally:
            lock_connection.close()
            _drop_database(database)


@pytest.mark.asyncio
async def test_runner_records_partial_ddl_failure_and_refuses_automatic_retry(tmp_path: Path):
    database = _create_database()
    try:
        migrations = _write_migrations(
            tmp_path,
            [
                (
                    "20261110_runner_partial",
                    "CREATE TABLE partial_probe (id INT NOT NULL PRIMARY KEY) ENGINE=InnoDB; "
                    "ALTER TABLE missing_runner_table ADD COLUMN unsafe_retry INT;",
                )
            ],
        )
        url = _database_url(database)
        with pytest.raises(MigrationExecutionError):
            await apply_migrations(
                url, repository_root=tmp_path, migrations=migrations
            )

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status, error_type FROM platform_schema_migrations "
                    "WHERE revision = %s",
                    (migrations[0].revision,),
                )
                row = cursor.fetchone()
                assert row[0] == "failed"
                assert row[1]
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'partial_probe'",
                    (database,),
                )
                assert cursor.fetchone()[0] == 1

        # MySQL DDL 已部分提交；Runner 不得猜测性重跑。
        with pytest.raises(MigrationLedgerError, match="manual DDL recovery is required"):
            await apply_migrations(
                url, repository_root=tmp_path, migrations=migrations
            )
    finally:
        _drop_database(database)


@pytest.mark.asyncio
async def test_runner_rejects_wrong_same_name_ledger_table(tmp_path: Path):
    database = _create_database()
    try:
        migrations = _write_migrations(
            tmp_path,
            [("20261110_runner_guard", "CREATE TABLE must_not_run (id INT PRIMARY KEY);")],
        )
        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE platform_schema_migrations ("
                    "revision VARCHAR(64) NOT NULL PRIMARY KEY"
                    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )

        with pytest.raises(MigrationRunnerError, match="ledger"):
            await apply_migrations(
                _database_url(database),
                repository_root=tmp_path,
                migrations=migrations,
            )

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'must_not_run'",
                    (database,),
                )
                assert cursor.fetchone()[0] == 0
    finally:
        _drop_database(database)


def test_runner_rejects_reusing_application_database_account():
    url = "mysql+aiomysql://same_user:secret@127.0.0.1:3306/platform"
    with pytest.raises(MigrationRunnerError, match="独立于应用运行账号"):
        from app.db.migrations.runner import _ensure_distinct_database_account
        from sqlalchemy.engine import make_url

        _ensure_distinct_database_account(make_url(url), url)
