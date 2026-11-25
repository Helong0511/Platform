"""CPL scope mutex 与活动唯一约束的真实 MySQL 8.0 集成测试。

仅允许在 GitHub Actions 临时 loopback platform_ci 上创建/删除隔离测试数据库。
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import uuid
from pathlib import Path
from urllib.parse import quote_plus

import pymysql
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.migrations.sql_parser import split_mysql_statements
from app.services.cpl.deduction.helpers import lock_deduction_scopes


MYSQL_HOST = os.getenv("MYSQL_INTEGRATION_HOST")
MYSQL_DATABASE = os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci")
MYSQL_PORT = int(os.getenv("MYSQL_INTEGRATION_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_INTEGRATION_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_INTEGRATION_PASSWORD", "")


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip()).is_loopback
    except ValueError:
        return False


_SAFE_MYSQL_TARGET = (
    os.getenv("UNIT_TEST") == "1"
    and os.getenv("GITHUB_ACTIONS") == "true"
    and os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _is_loopback_host(MYSQL_HOST)
    and MYSQL_DATABASE == "platform_ci"
)

if (
    os.getenv("GITHUB_ACTIONS") == "true"
    or (os.getenv("UNIT_TEST") == "1" and MYSQL_HOST)
) and not _SAFE_MYSQL_TARGET:
    raise RuntimeError(
        "拒绝执行 CPL scope MySQL 集成测试：必须使用 loopback MySQL platform_ci，"
        "并显式设置 MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS=1"
    )

pytestmark = pytest.mark.skipif(
    not _SAFE_MYSQL_TARGET,
    reason="仅在 GitHub Actions 临时 MySQL platform_ci 服务中运行",
)


MIGRATION_FILES = (
    "sql/migrations/20261125_cpl_deduction_scope_locks.sql",
    "sql/migrations/20261125_cpl_deduction_scope_restrict_fks.sql",
    "sql/migrations/20261125_cpl_deduction_scope_unique.sql",
)


def _admin_connection():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=20,
        write_timeout=10,
    )


def _create_database() -> str:
    database = f"platform_ci_cpl_scope_{uuid.uuid4().hex[:12]}"
    connection = _admin_connection()
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
    connection = _admin_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION lock_wait_timeout = 10")
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


def _create_base_schema(database: str) -> None:
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=20,
        write_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            for table in ("conversion_deduction_configs", "advertisers", "offers", "publishers"):
                cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
            for table in ("advertisers", "offers", "publishers"):
                cursor.execute(
                    f"CREATE TABLE `{table}` ("
                    "id INT NOT NULL AUTO_INCREMENT PRIMARY KEY"
                    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )
            seed_ids = (9, 101, 202, 303, 404, 505)
            for table in ("advertisers", "offers", "publishers"):
                values = ", ".join(f"({value})" for value in seed_ids)
                cursor.execute(f"INSERT INTO `{table}` (id) VALUES {values}")
            cursor.execute(
                """
                CREATE TABLE conversion_deduction_configs (
                    id INT NOT NULL AUTO_INCREMENT,
                    advertiser_id INT NULL,
                    offer_id INT NULL,
                    publisher_id INT NULL,
                    is_active TINYINT(1) NULL DEFAULT 1,
                    PRIMARY KEY (id),
                    CONSTRAINT fk_scope_test_advertiser
                        FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
                        ON DELETE CASCADE,
                    CONSTRAINT fk_scope_test_offer
                        FOREIGN KEY (offer_id) REFERENCES offers(id)
                        ON DELETE CASCADE,
                    CONSTRAINT fk_scope_test_publisher
                        FOREIGN KEY (publisher_id) REFERENCES publishers(id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
    finally:
        connection.close()


def _execute_migration(database: str, migration_path: str) -> None:
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=20,
        write_timeout=10,
    )
    try:
        migration = Path(migration_path).read_text(encoding="utf-8")
        with connection.cursor() as cursor:
            for statement in split_mysql_statements(migration):
                cursor.execute(statement)
    finally:
        connection.close()


def _initialize_schema(database: str) -> None:
    _create_base_schema(database)
    for migration_path in MIGRATION_FILES:
        _execute_migration(database, migration_path)


def _create_engine(database: str):
    user = quote_plus(MYSQL_USER)
    password = quote_plus(MYSQL_PASSWORD)
    return create_async_engine(
        f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}"
        "?charset=utf8mb4",
        isolation_level="REPEATABLE READ",
        pool_pre_ping=True,
        pool_size=55,
        max_overflow=5,
    )


async def _with_database(callback):
    database = _create_database()
    engine = None
    try:
        _initialize_schema(database)
        engine = _create_engine(database)
        factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        await callback(database, factory)
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_database(database)


@pytest.mark.asyncio
async def test_mysql_no_config_race_is_serialized_against_first_config_create():
    async def scenario(database, factory):
        async with factory() as postback:
            await lock_deduction_scopes(postback, [("offer", 101)])
            existing = await postback.scalar(
                text(
                    "SELECT id FROM conversion_deduction_configs "
                    "WHERE offer_id = 101 AND is_active = 1 FOR UPDATE"
                )
            )
            assert existing is None

            started = asyncio.Event()

            async def create_first_config():
                async with factory() as writer:
                    started.set()
                    await lock_deduction_scopes(writer, [("offer", 101)])
                    await writer.execute(
                        text(
                            "INSERT INTO conversion_deduction_configs "
                            "(offer_id, is_active) VALUES (101, 1)"
                        )
                    )
                    await writer.commit()

            task = asyncio.create_task(create_first_config())
            await asyncio.wait_for(started.wait(), timeout=5)
            await asyncio.sleep(0.2)
            assert not task.done(), "配置创建未等待 Postback scope 锁释放"

            await postback.commit()
            await asyncio.wait_for(task, timeout=10)

        async with factory() as verify:
            count = await verify.scalar(
                text(
                    "SELECT COUNT(*) FROM conversion_deduction_configs "
                    "WHERE offer_id = 101 AND is_active = 1"
                )
            )
            assert count == 1

    await _with_database(scenario)


@pytest.mark.asyncio
async def test_mysql_repeatable_read_uses_current_read_after_stale_snapshot():
    async def scenario(database, factory):
        async with factory() as stale_reader:
            # 建立旧 REPEATABLE READ 快照。
            assert await stale_reader.scalar(
                text("SELECT COUNT(*) FROM conversion_deduction_configs")
            ) == 0

            async with factory() as writer:
                await lock_deduction_scopes(writer, [("offer", 202)])
                await writer.execute(
                    text(
                        "INSERT INTO conversion_deduction_configs "
                        "(offer_id, is_active) VALUES (202, 1)"
                    )
                )
                await writer.commit()

            # 锁行获取后必须使用锁定读，不能继续看到锁前旧快照。
            await lock_deduction_scopes(stale_reader, [("offer", 202)])
            current = await stale_reader.scalar(
                text(
                    "SELECT id FROM conversion_deduction_configs "
                    "WHERE offer_id = 202 AND is_active = 1 FOR UPDATE"
                )
            )
            assert current is not None
            await stale_reader.rollback()

    await _with_database(scenario)


@pytest.mark.asyncio
async def test_mysql_reverse_batch_scope_order_does_not_deadlock():
    async def scenario(database, factory):
        async def lock_in_order(scopes):
            async with factory() as session:
                await lock_deduction_scopes(session, scopes)
                await asyncio.sleep(0.05)
                await session.commit()

        await asyncio.wait_for(
            asyncio.gather(
                lock_in_order([("publisher", 9), ("offer", 9)]),
                lock_in_order([("offer", 9), ("publisher", 9)]),
            ),
            timeout=10,
        )

    await _with_database(scenario)


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", [2, 10, 50])
async def test_mysql_concurrent_first_config_creation_has_one_winner(concurrency):
    async def scenario(database, factory):
        async def create_if_missing(index):
            async with factory() as session:
                await lock_deduction_scopes(session, [("offer", 303)])
                existing = await session.scalar(
                    text(
                        "SELECT id FROM conversion_deduction_configs "
                        "WHERE offer_id = 303 AND is_active = 1 FOR UPDATE"
                    )
                )
                if existing is None:
                    await session.execute(
                        text(
                            "INSERT INTO conversion_deduction_configs "
                            "(offer_id, is_active) VALUES (303, 1)"
                        )
                    )
                await session.commit()

        await asyncio.wait_for(
            asyncio.gather(*(create_if_missing(i) for i in range(concurrency))),
            timeout=30,
        )
        async with factory() as verify:
            count = await verify.scalar(
                text(
                    "SELECT COUNT(*) FROM conversion_deduction_configs "
                    "WHERE offer_id = 303 AND is_active = 1"
                )
            )
            assert count == 1

    await _with_database(scenario)


@pytest.mark.asyncio
async def test_mysql_generated_unique_keys_and_parent_foreign_keys_are_enforced():
    async def scenario(database, factory):
        connection = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=database,
            charset="utf8mb4",
            autocommit=True,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO conversion_deduction_configs (offer_id, is_active) "
                    "VALUES (404, 1)"
                )
                with pytest.raises(pymysql.err.IntegrityError):
                    cursor.execute(
                        "INSERT INTO conversion_deduction_configs (offer_id, is_active) "
                        "VALUES (404, 1)"
                    )
                with pytest.raises(pymysql.err.IntegrityError):
                    cursor.execute(
                        "INSERT INTO conversion_deduction_configs (is_active) VALUES (1)"
                    )
                with pytest.raises(pymysql.err.IntegrityError):
                    cursor.execute("DELETE FROM offers WHERE id = 404")
        finally:
            connection.close()

    await _with_database(scenario)


@pytest.mark.asyncio
async def test_mysql_unique_migration_refuses_historical_active_scope_collisions():
    database = _create_database()
    try:
        _create_base_schema(database)
        _execute_migration(database, MIGRATION_FILES[0])
        _execute_migration(database, MIGRATION_FILES[1])

        connection = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=database,
            charset="utf8mb4",
            autocommit=True,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO conversion_deduction_configs (offer_id, is_active) "
                    "VALUES (505, 1), (505, 1)"
                )
        finally:
            connection.close()

        with pytest.raises(pymysql.err.ProgrammingError):
            _execute_migration(database, MIGRATION_FILES[2])

        verify = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=database,
            charset="utf8mb4",
            autocommit=True,
        )
        try:
            with verify.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM conversion_deduction_configs "
                    "WHERE offer_id = 505 AND is_active = 1"
                )
                assert cursor.fetchone()[0] == 2
        finally:
            verify.close()
    finally:
        _drop_database(database)
