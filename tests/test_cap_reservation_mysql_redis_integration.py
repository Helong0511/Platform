"""跨存储 Cap Reservation 故障恢复集成测试。

只使用 CI 显式提供的临时 MySQL 8.0、Redis DB14；每个测试创建并销毁独立数据库。
不会读取应用 DATABASE_URL，也不会连接生产服务。
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pymysql
import pytest
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.cap.redis_counter import RedisCapManager
from app.core.utils import get_app_now_naive
from app.models.cap_reservation import CapReservation
from app.services import cap_reservation_ledger as ledger_module
from app.services import cap_reservation_recovery as recovery_module
from app.services.cap_reservation_ledger import CapReservationLedger


MYSQL_HOST = os.getenv("MYSQL_INTEGRATION_HOST")
REDIS_URL = os.getenv("REDIS_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not MYSQL_HOST or not REDIS_URL,
    reason="仅在显式配置的隔离 MySQL + Redis 集成环境中运行",
)


def _create_isolated_mysql_database() -> str:
    database = f"ci_cap_recovery_{uuid.uuid4().hex[:12]}"
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=int(os.getenv("MYSQL_INTEGRATION_PORT", "3306")),
        user=os.getenv("MYSQL_INTEGRATION_USER", "root"),
        password=os.getenv("MYSQL_INTEGRATION_PASSWORD", ""),
        database=os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci"),
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()
    return database


def _drop_isolated_mysql_database(database: str) -> None:
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=int(os.getenv("MYSQL_INTEGRATION_PORT", "3306")),
        user=os.getenv("MYSQL_INTEGRATION_USER", "root"),
        password=os.getenv("MYSQL_INTEGRATION_PASSWORD", ""),
        database=os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci"),
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


def _initialize_isolated_schema(database: str) -> None:
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=int(os.getenv("MYSQL_INTEGRATION_PORT", "3306")),
        user=os.getenv("MYSQL_INTEGRATION_USER", "root"),
        password=os.getenv("MYSQL_INTEGRATION_PASSWORD", ""),
        database=database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )
    try:
        migration = Path(
            "sql/migrations/20261111_cap_reservation_ledger.sql"
        ).read_text(encoding="utf-8")
        statements = [
            item.strip()
            for item in "\n".join(
                line for line in migration.splitlines()
                if not line.lstrip().startswith("--")
            ).split(";")
            if item.strip()
        ]
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
                if cursor.description:
                    cursor.fetchall()
            # 只创建恢复查询所需的最小正式事件表结构，避免创建整个生产模型图。
            cursor.execute(
                """
                CREATE TABLE postback_conversions (
                    id INT NOT NULL AUTO_INCREMENT,
                    platform VARCHAR(50) NOT NULL,
                    conversion_id VARCHAR(255) NOT NULL,
                    event_name VARCHAR(100) NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY uq_ci_postback_event (platform, conversion_id, event_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
                """
            )
    finally:
        connection.close()


async def _run_recovery_scenario(monkeypatch, *, conversion_committed: bool):
    database = _create_isolated_mysql_database()
    engine = None
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        _initialize_isolated_schema(database)
        password = quote_plus(os.getenv("MYSQL_INTEGRATION_PASSWORD", ""))
        user = quote_plus(os.getenv("MYSQL_INTEGRATION_USER", "root"))
        engine = create_async_engine(
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:"
            f"{int(os.getenv('MYSQL_INTEGRATION_PORT', '3306'))}/{database}"
            "?charset=utf8mb4",
            pool_pre_ping=True,
        )
        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        monkeypatch.setattr(ledger_module, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(recovery_module, "AsyncSessionLocal", session_factory)

        async def isolated_redis_client():
            return redis

        from app.core.cap import redis_counter
        monkeypatch.setattr(redis_counter, "get_redis_client", isolated_redis_client)

        assert await redis.ping() is True
        offer_id = int(uuid.uuid4().int % 900_000_000) + 100_000_000
        publisher_id = int(uuid.uuid4().int % 900_000_000) + 100_000_000
        conversion_id = f"ci-conversion-{uuid.uuid4().hex}"
        business_date = get_app_now_naive().date()

        row, claimed, owner = await CapReservationLedger.prepare_and_claim(
            platform="ci",
            conversion_id=conversion_id,
            event_name="purchase",
            offer_id=offer_id,
            publisher_id=publisher_id,
            cap_kind="daily",
            business_date=business_date,
        )
        assert claimed is True
        assert owner

        reserved = await RedisCapManager.check_and_increment_daily(
            offer_id,
            limit=10,
            publisher_id=publisher_id,
            initial_value=0,
            reservation_id=row.reservation_key,
            reservation_date=datetime.combine(business_date, time(12, 0)),
        )
        assert reserved is True
        await CapReservationLedger.mark_reserved(row.reservation_key, owner)

        if conversion_committed:
            async with session_factory() as session:
                await session.execute(
                    __import__("sqlalchemy").text(
                        "INSERT INTO postback_conversions "
                        "(platform, conversion_id, event_name) "
                        "VALUES (:platform, :conversion_id, :event_name)"
                    ),
                    {
                        "platform": "ci",
                        "conversion_id": conversion_id,
                        "event_name": "purchase",
                    },
                )
                await session.commit()

        # 模拟 worker 在 Redis 预留后被直接 kill：只留下过期的 RESERVED 账本。
        async with session_factory() as session:
            await session.execute(
                update(CapReservation)
                .where(CapReservation.reservation_key == row.reservation_key)
                .values(lease_expires_at=get_app_now_naive() - timedelta(seconds=1))
            )
            await session.commit()

        stats = await recovery_module.recover_cap_reservations(batch_size=10)

        async with session_factory() as session:
            recovered = await session.scalar(
                select(CapReservation).where(
                    CapReservation.reservation_key == row.reservation_key
                )
            )

        counter_value = await redis.get(row.redis_counter_key)
        token_value = await redis.get(row.redis_token_key)
        return {
            "stats": stats,
            "state": recovered.state,
            "redis_reserved": recovered.redis_reserved,
            "redis_token_cleaned": recovered.redis_token_cleaned,
            "counter_value": counter_value,
            "token_value": token_value,
        }
    finally:
        await redis.aclose()
        if engine is not None:
            await engine.dispose()
        _drop_isolated_mysql_database(database)


@pytest.mark.asyncio
async def test_mysql_redis_recovery_rolls_back_orphan_reservation_after_worker_crash(monkeypatch):
    result = await _run_recovery_scenario(
        monkeypatch,
        conversion_committed=False,
    )

    assert result["state"] == "ROLLED_BACK"
    assert result["redis_reserved"] is False
    assert result["redis_token_cleaned"] is True
    assert result["counter_value"] == "0"
    assert result["token_value"] is None
    assert result["stats"]["rolled_back"] == 1


@pytest.mark.asyncio
async def test_mysql_redis_recovery_keeps_committed_conversion_and_cleans_token(monkeypatch):
    result = await _run_recovery_scenario(
        monkeypatch,
        conversion_committed=True,
    )

    assert result["state"] == "COMMITTED"
    assert result["redis_reserved"] is True
    assert result["redis_token_cleaned"] is True
    assert result["counter_value"] == "1"
    assert result["token_value"] is None
    assert result["stats"]["committed"] == 1
    assert result["stats"]["tokens_cleaned"] == 1
