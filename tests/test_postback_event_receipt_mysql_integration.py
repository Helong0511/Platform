"""真实 MySQL REPEATABLE READ 下的 Postback 扣量事件收据幂等集成测试。

只使用 CI 显式提供的 loopback MySQL platform_ci，并为每个测试创建独立数据库。
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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.postback.validators.duplicate_checker import DuplicateChecker
from app.db.migrations.sql_parser import split_mysql_statements


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
        "拒绝执行 Postback 收据 MySQL 集成测试：必须使用 loopback MySQL platform_ci，"
        "并显式设置 MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS=1"
    )

pytestmark = pytest.mark.skipif(
    not _SAFE_MYSQL_TARGET,
    reason="仅在 GitHub Actions 临时 MySQL platform_ci 服务中运行",
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
    database = f"platform_ci_postback_receipt_{uuid.uuid4().hex[:12]}"
    connection = _admin_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
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


def _initialize_schema(database: str) -> None:
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
            cursor.execute(
                """
                CREATE TABLE postback_conversions (
                    id INT NOT NULL AUTO_INCREMENT,
                    platform VARCHAR(50) NOT NULL,
                    conversion_id VARCHAR(255) NOT NULL,
                    event_name VARCHAR(100) NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY uq_postback_platform_conversion_event
                        (platform, conversion_id, event_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
                """
            )
            migration = Path(
                "sql/migrations/20261124_postback_event_deduction_receipts.sql"
            ).read_text(encoding="utf-8")
            for statement in split_mysql_statements(migration):
                cursor.execute(statement)
    finally:
        connection.close()


async def _run_scenario(scenario: str) -> None:
    database = _create_database()
    engine = None
    try:
        _initialize_schema(database)
        user = quote_plus(MYSQL_USER)
        password = quote_plus(MYSQL_PASSWORD)
        engine = create_async_engine(
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}"
            "?charset=utf8mb4",
            isolation_level="REPEATABLE READ",
            pool_pre_ping=True,
        )
        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        identity = {
            "platform": "integration_partner",
            "conversion_id": f"receipt-{uuid.uuid4().hex}",
            "event_name": "purchase",
        }

        async with session_factory() as first:
            duplicate = await DuplicateChecker.is_duplicate(**identity, db=first)
            assert duplicate is False

            if scenario == "volume_deducted":
                # 命中扣量：不插入正式转化，只提交持久收据。
                await first.commit()

                async with session_factory() as retry:
                    duplicate_retry = await DuplicateChecker.is_duplicate(
                        **identity,
                        db=retry,
                    )
                    assert duplicate_retry is True
                    await retry.rollback()
                return

            # 普通转化：正式记录插入与临时收据删除必须在同一事务提交。
            waiting = asyncio.create_task(
                _concurrent_normal_retry(session_factory, identity)
            )
            # 给第二个连接时间完成首次普通 SELECT 并阻塞在唯一收据 INSERT。
            await asyncio.sleep(0.25)
            await first.execute(
                text(
                    "INSERT INTO postback_conversions "
                    "(platform, conversion_id, event_name) "
                    "VALUES (:platform, :conversion_id, :event_name)"
                ),
                identity,
            )
            await DuplicateChecker.release_receipt(**identity, db=first)
            await first.commit()

            duplicate_retry = await asyncio.wait_for(waiting, timeout=10)
            assert duplicate_retry is True
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_database(database)


async def _concurrent_normal_retry(session_factory, identity) -> bool:
    async with session_factory() as session:
        duplicate = await DuplicateChecker.is_duplicate(**identity, db=session)
        await session.commit()
        return duplicate


@pytest.mark.asyncio
async def test_mysql_receipt_prevents_replay_of_volume_deducted_event():
    await _run_scenario("volume_deducted")


@pytest.mark.asyncio
async def test_mysql_repeatable_read_closes_normal_conversion_receipt_release_race():
    await _run_scenario("normal_conversion")
