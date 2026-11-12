"""跨存储 Cap Reservation 故障恢复集成测试。

只使用 CI 显式提供的临时 MySQL 8.0、Redis DB14；每个测试创建并销毁独立数据库。
不会读取应用 DATABASE_URL，也不会连接生产服务。
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

import pymysql
import pytest
from redis.asyncio import Redis
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.cap.redis_counter import RedisCapManager
from app.core.utils import get_app_now_naive
from app.core.postback.processor import PostbackProcessor
from app.core.postback.checks.cap_checker import CapChecker
from app.models.cap_reservation import CapReservation
from app.services import cap_reservation_ledger as ledger_module
from app.services import cap_reservation_recovery as recovery_module
from app.services.cap_reservation_ledger import CapReservationLedger


MYSQL_HOST = os.getenv("MYSQL_INTEGRATION_HOST")
MYSQL_DATABASE = os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci")
REDIS_URL = os.getenv("REDIS_INTEGRATION_URL")


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip()).is_loopback
    except ValueError:
        return False


def _is_isolated_redis_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme in {"redis", "rediss"}
            and _is_loopback_host(parsed.hostname)
            and parsed.port in (None, 6379)
            and parsed.path.strip("/") == "14"
        )
    except ValueError:
        return False


_SAFE_INTEGRATION_TARGETS = (
    os.getenv("UNIT_TEST") == "1"
    and os.getenv("GITHUB_ACTIONS") == "true"
    and os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and os.getenv("REDIS_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _is_loopback_host(MYSQL_HOST)
    and MYSQL_DATABASE == "platform_ci"
    and _is_isolated_redis_url(REDIS_URL)
)

# 该测试会 CREATE/DROP 数据库并写入/删除 Redis key。CI 环境若配置缺失或目标非本机，
# 必须失败关闭；本地未显式启用时则跳过，绝不尝试连接外部服务。
if (os.getenv("GITHUB_ACTIONS") == "true" or (os.getenv("UNIT_TEST") == "1" and (MYSQL_HOST or REDIS_URL))) and not _SAFE_INTEGRATION_TARGETS:
    raise RuntimeError(
        "拒绝执行 Cap Reservation 集成测试：必须使用 loopback MySQL platform_ci、"
        "loopback Redis DB14，并显式启用两个隔离测试授权变量"
    )

pytestmark = pytest.mark.skipif(
    not _SAFE_INTEGRATION_TARGETS,
    reason="仅在 GitHub Actions 临时 MySQL platform_ci + Redis DB14 服务中运行",
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


async def _run_recovery_scenario(monkeypatch, *, conversion_committed: bool, workers: int = 1):
    database = _create_isolated_mysql_database()
    engine = None
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    redis_keys = []
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
        redis_keys.extend([row.redis_counter_key, row.redis_token_key])

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
                    text(
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

        if workers == 1:
            stats = await recovery_module.recover_cap_reservations(batch_size=10)
        else:
            stats = await asyncio.gather(*(
                recovery_module.recover_cap_reservations(batch_size=10)
                for _ in range(workers)
            ))

        # ROLLED_BACK 先提交 MySQL 终态并保留 Redis 墓碑；下一轮恢复再清理墓碑。
        cleanup_stats = None
        if not conversion_committed:
            cleanup_stats = await recovery_module.recover_cap_reservations(batch_size=10)

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
            "cleanup_stats": cleanup_stats,
            "state": recovered.state,
            "redis_reserved": recovered.redis_reserved,
            "redis_token_cleaned": recovered.redis_token_cleaned,
            "counter_value": counter_value,
            "token_value": token_value,
        }
    finally:
        if redis_keys:
            await redis.delete(*redis_keys)
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
    assert result["cleanup_stats"]["tokens_cleaned"] == 1


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



@pytest.mark.asyncio
async def test_mysql_commit_response_lost_after_commit_preserves_cap_reservation(monkeypatch):
    """MySQL 已提交但客户端收到断线异常时，不得回退 Redis Cap。"""
    database = _create_isolated_mysql_database()
    engine = None
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
        conversion_id = 990001
        async with session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO postback_conversions "
                    "(id, platform, conversion_id, event_name) "
                    "VALUES (:id, :platform, :conversion_id, :event_name)"
                ),
                {
                    "id": conversion_id,
                    "platform": "ci",
                    "conversion_id": "commit-response-lost",
                    "event_name": "purchase",
                },
            )

            class CommitThenDisconnect:
                async def commit(self):
                    await session.commit()
                    # 模拟 MySQL COMMIT 已成功，但响应在网络中丢失。
                    raise OSError("simulated connection loss after COMMIT")

                async def rollback(self):
                    await session.rollback()

                async def execute(self, statement):
                    return await session.execute(statement)

            finalized = []
            rolled_back = []

            async def renew_lease(*args, **kwargs):
                return None

            async def finalize(*args, **kwargs):
                finalized.append((args, kwargs))

            async def rollback_reservations(reservations):
                rolled_back.extend(reservations)

            from app.core.postback import processor as processor_module
            monkeypatch.setattr(processor_module.CapReservationLedger, "renew_lease", renew_lease)
            monkeypatch.setattr(processor_module.CapReservationLedger, "finalize", finalize)
            monkeypatch.setattr(CapChecker, "rollback_reservations", rollback_reservations)

            reservations = [
                (
                    "daily", 77, 12, datetime(2026, 11, 11),
                    "a" * 64, "b" * 64, "ci-lease-owner", True,
                )
            ]
            with pytest.raises(OSError, match="after COMMIT"):
                await PostbackProcessor._commit_conversion_with_cap_reconciliation(
                    db=CommitThenDisconnect(),
                    conversion_id=conversion_id,
                    cap_reservations=reservations,
                )

            assert rolled_back == []
            assert finalized == [
                (("b" * 64, "COMMITTED"), {"lease_owner": "ci-lease-owner"})
            ]
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_mysql_database(database)


@pytest.mark.asyncio
async def test_mysql_redis_recovery_retries_needs_reconciliation_after_backoff(monkeypatch):
    """NEEDS_RECONCILIATION 到期后，真实 MySQL + Redis 恢复应安全撤销孤儿预留。"""
    database = _create_isolated_mysql_database()
    engine = None
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    redis_keys = []
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
        business_date = get_app_now_naive().date()
        row, claimed, owner = await CapReservationLedger.prepare_and_claim(
            platform="ci",
            conversion_id=f"needs-reconciliation-{uuid.uuid4().hex}",
            event_name="purchase",
            offer_id=offer_id,
            publisher_id=publisher_id,
            cap_kind="daily",
            business_date=business_date,
        )
        assert claimed is True
        assert owner
        redis_keys.extend([row.redis_counter_key, row.redis_token_key])

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
        await CapReservationLedger.mark_needs_reconciliation(
            row.reservation_key,
            "simulated temporary Redis uncertainty",
            lease_owner=owner,
        )

        async with session_factory() as session:
            await session.execute(
                update(CapReservation)
                .where(CapReservation.reservation_key == row.reservation_key)
                .values(updated_at=get_app_now_naive() - timedelta(minutes=6))
            )
            await session.commit()

        stats = await recovery_module.recover_cap_reservations(batch_size=10)
        async with session_factory() as session:
            recovered = await session.scalar(
                select(CapReservation).where(
                    CapReservation.reservation_key == row.reservation_key
                )
            )

        assert recovered.state == "ROLLED_BACK"
        assert await redis.get(row.redis_counter_key) == "0"
        assert await redis.get(row.redis_token_key) == "ROLLED_BACK"
        assert stats["claimed"] == 1
        assert stats["rolled_back"] == 1
        assert stats["needs_reconciliation"] == 0

        # 终态提交后由下一轮恢复 Worker 清理墓碑。
        cleanup_stats = await recovery_module.recover_cap_reservations(batch_size=10)
        async with session_factory() as session:
            recovered = await session.scalar(
                select(CapReservation).where(
                    CapReservation.reservation_key == row.reservation_key
                )
            )
        assert recovered.redis_token_cleaned is True
        assert await redis.get(row.redis_token_key) is None
        assert cleanup_stats["tokens_cleaned"] == 1
    finally:
        if redis_keys:
            await redis.delete(*redis_keys)
        await redis.aclose()
        if engine is not None:
            await engine.dispose()
        _drop_isolated_mysql_database(database)


@pytest.mark.asyncio
async def test_mysql_concurrent_claim_allows_only_one_owner_for_same_reservation(monkeypatch):
    """并发首次插入相同稳定键时，唯一键/gap-lock 竞争只能产生一个有效 owner。"""
    database = _create_isolated_mysql_database()
    engine = None
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

        identity = {
            "platform": "ci",
            "conversion_id": f"concurrent-{uuid.uuid4().hex}",
            "event_name": "purchase",
            "offer_id": int(uuid.uuid4().int % 900_000_000) + 100_000_000,
            "publisher_id": int(uuid.uuid4().int % 900_000_000) + 100_000_000,
            "cap_kind": "total",
            "business_date": None,
        }
        results = await asyncio.gather(
            CapReservationLedger.prepare_and_claim(**identity),
            CapReservationLedger.prepare_and_claim(**identity),
        )

        assert sum(1 for _row, claimed, _owner in results if claimed) == 1
        assert results[0][0].reservation_key == results[1][0].reservation_key
        assert sum(1 for _row, _claimed, owner in results if owner) == 1

        async with session_factory() as session:
            rows = (
                await session.scalars(
                    select(CapReservation).where(
                        CapReservation.reservation_key == results[0][0].reservation_key
                    )
                )
            ).all()
        assert len(rows) == 1
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_mysql_database(database)



@pytest.mark.asyncio
async def test_mysql_recovery_workers_cannot_double_rollback_same_reservation(monkeypatch):
    result = await _run_recovery_scenario(
        monkeypatch,
        conversion_committed=False,
        workers=2,
    )

    stats = result["stats"]
    assert sum(item["claimed"] for item in stats) == 1
    assert sum(item["rolled_back"] for item in stats) == 1
    assert result["state"] == "ROLLED_BACK"
    assert result["counter_value"] == "0"
    assert result["token_value"] is None



@pytest.mark.asyncio
async def test_wrong_lease_owner_cannot_finalize_or_delete_reservation_token(monkeypatch):
    database = _create_isolated_mysql_database()
    engine = None
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    redis_keys = []
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
        from app.core.cap import redis_counter

        async def isolated_redis_client():
            return redis

        monkeypatch.setattr(redis_counter, "get_redis_client", isolated_redis_client)

        row, claimed, owner = await CapReservationLedger.prepare_and_claim(
            platform="ci",
            conversion_id=f"wrong-owner-{uuid.uuid4().hex}",
            event_name="purchase",
            offer_id=int(uuid.uuid4().int % 900_000_000) + 100_000_000,
            publisher_id=None,
            cap_kind="total",
            business_date=None,
        )
        assert claimed is True
        redis_keys.append(row.redis_token_key)
        await redis.set(row.redis_token_key, "1")

        with pytest.raises(RuntimeError, match="lease owner"):
            await CapReservationLedger.finalize(
                row.reservation_key,
                "COMMITTED",
                lease_owner="not-the-owner",
            )

        async with session_factory() as session:
            current = await session.scalar(
                select(CapReservation).where(
                    CapReservation.reservation_key == row.reservation_key
                )
            )

        assert current.state == "PREPARED"
        assert current.lease_owner == owner
        assert await redis.get(row.redis_token_key) == "1"
    finally:
        if redis_keys:
            await redis.delete(*redis_keys)
        await redis.aclose()
        if engine is not None:
            await engine.dispose()
        _drop_isolated_mysql_database(database)


@pytest.mark.asyncio
async def test_expired_lease_is_not_reclaimed_by_duplicate_postback(monkeypatch):
    """租约过期不代表旧 worker 已死亡；只能由恢复 Worker 核验后接管。"""
    database = _create_isolated_mysql_database()
    engine = None
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

        identity = {
            "platform": "ci",
            "conversion_id": f"expired-lease-{uuid.uuid4().hex}",
            "event_name": "purchase",
            "offer_id": int(uuid.uuid4().int % 900_000_000) + 100_000_000,
            "publisher_id": None,
            "cap_kind": "total",
            "business_date": None,
        }
        first, claimed, first_owner = await CapReservationLedger.prepare_and_claim(**identity)
        assert claimed is True
        assert first_owner

        async with session_factory() as session:
            await session.execute(
                update(CapReservation)
                .where(CapReservation.reservation_key == first.reservation_key)
                .values(lease_expires_at=get_app_now_naive() - timedelta(seconds=1))
            )
            await session.commit()

        duplicate, duplicate_claimed, duplicate_owner = (
            await CapReservationLedger.prepare_and_claim(**identity)
        )

        assert duplicate.reservation_key == first.reservation_key
        assert duplicate_claimed is False
        assert duplicate_owner is None
        assert duplicate.lease_owner == first_owner
        assert duplicate.state == "PREPARED"
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_mysql_database(database)


@pytest.mark.asyncio
async def test_mysql_tcp_proxy_drops_real_commit_ack_and_preserves_cap_reservation(monkeypatch):
    """通过 TCP 代理丢弃真实 MySQL COMMIT OK 包，验证断线后的 fail-safe 行为。"""
    database = _create_isolated_mysql_database()
    direct_engine = None
    proxy_engine = None
    proxy_server = None
    commit_seen = asyncio.Event()
    ack_dropped = asyncio.Event()
    observed_queries = []
    try:
        _initialize_isolated_schema(database)
        password = quote_plus(os.getenv("MYSQL_INTEGRATION_PASSWORD", ""))
        user = quote_plus(os.getenv("MYSQL_INTEGRATION_USER", "root"))
        mysql_port = int(os.getenv("MYSQL_INTEGRATION_PORT", "3306"))
        direct_url = (
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{mysql_port}/{database}"
            "?charset=utf8mb4"
        )
        direct_engine = create_async_engine(direct_url, pool_pre_ping=True)

        async def proxy_client(client_reader, client_writer):
            upstream_reader, upstream_writer = await asyncio.open_connection(
                MYSQL_HOST, mysql_port
            )

            async def forward_client_to_mysql():
                buffer = bytearray()
                while True:
                    chunk = await client_reader.read(65536)
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    # MySQL packet = 3-byte payload length + sequence + payload。
                    while len(buffer) >= 4:
                        payload_length = int.from_bytes(buffer[:3], "little")
                        packet_length = payload_length + 4
                        if len(buffer) < packet_length:
                            break
                        packet = bytes(buffer[:packet_length])
                        payload = packet[4:]
                        upstream_writer.write(packet)
                        # 只识别 COM_QUERY 的完整 COMMIT 语句，避免匹配 SQL 参数文本。
                        if payload[:1] == b"\x03":
                            observed_queries.append(payload[1:].decode("utf-8", "replace")[:120])
                            if payload[1:].lstrip().upper().startswith(b"COMMIT"):
                                commit_seen.set()
                        await upstream_writer.drain()
                        del buffer[:packet_length]
                if buffer:
                    upstream_writer.write(buffer)
                    await upstream_writer.drain()
                try:
                    upstream_writer.write_eof()
                except (AttributeError, OSError, RuntimeError):
                    pass

            async def forward_mysql_to_client():
                # 按 MySQL packet framing 解析响应，只丢弃 COMMIT 对应的 OK(0x00) 包；
                # 不能因 COMMIT 已发出就误丢此前/其它命令的响应。
                response_buffer = bytearray()
                while True:
                    chunk = await upstream_reader.read(65536)
                    if not chunk:
                        break
                    response_buffer.extend(chunk)
                    while len(response_buffer) >= 4:
                        payload_length = int.from_bytes(response_buffer[:3], "little")
                        packet_length = payload_length + 4
                        if len(response_buffer) < packet_length:
                            break
                        packet = bytes(response_buffer[:packet_length])
                        payload = packet[4:]
                        del response_buffer[:packet_length]
                        if commit_seen.is_set() and payload[:1] == b"\x00":
                            # 只在确认收到 COMMIT 成功 OK 包时制造 ACK 丢失。
                            ack_dropped.set()
                            client_writer.close()
                            upstream_writer.close()
                            return
                        client_writer.write(packet)
                        await client_writer.drain()
                if response_buffer:
                    client_writer.write(response_buffer)
                    await client_writer.drain()

            try:
                await asyncio.gather(
                    forward_client_to_mysql(),
                    forward_mysql_to_client(),
                    return_exceptions=True,
                )
            finally:
                client_writer.close()
                upstream_writer.close()
                try:
                    await client_writer.wait_closed()
                except (OSError, RuntimeError):
                    pass
                try:
                    await upstream_writer.wait_closed()
                except (OSError, RuntimeError):
                    pass

        proxy_server = await asyncio.start_server(proxy_client, "127.0.0.1", 0)
        proxy_port = proxy_server.sockets[0].getsockname()[1]
        proxy_url = (
            f"mysql+aiomysql://{user}:{password}@127.0.0.1:{proxy_port}/{database}"
            "?charset=utf8mb4"
        )
        proxy_engine = create_async_engine(
            proxy_url,
            pool_pre_ping=False,
            connect_args={"connect_timeout": 5, "read_timeout": 5, "write_timeout": 5},
        )
        proxy_sessions = async_sessionmaker(
            bind=proxy_engine,
            expire_on_commit=False,
            autoflush=False,
        )

        conversion_id = 990002
        rolled_back = []
        finalized = []

        async def renew_lease(*args, **kwargs):
            return None

        async def finalize(*args, **kwargs):
            finalized.append((args, kwargs))

        async def rollback_reservations(reservations):
            rolled_back.extend(reservations)

        from app.core.postback import processor as processor_module
        monkeypatch.setattr(
            processor_module.CapReservationLedger, "renew_lease", renew_lease
        )
        monkeypatch.setattr(
            processor_module.CapReservationLedger, "finalize", finalize
        )
        monkeypatch.setattr(
            CapChecker, "rollback_reservations", rollback_reservations
        )

        reservations = [
            (
                "daily", 77, 12, datetime(2026, 11, 11),
                "a" * 64, "b" * 64, "ci-lease-owner", True,
            )
        ]
        async with proxy_sessions() as session:
            await session.execute(
                text(
                    "INSERT INTO postback_conversions "
                    "(id, platform, conversion_id, event_name) "
                    "VALUES (:id, :platform, :conversion_id, :event_name)"
                ),
                {
                    "id": conversion_id,
                    "platform": "ci",
                    "conversion_id": "tcp-proxy-commit-ack-lost",
                    "event_name": "purchase",
                },
            )
            commit_error = None
            try:
                await PostbackProcessor._commit_conversion_with_cap_reconciliation(
                    db=session,
                    conversion_id=conversion_id,
                    cap_reservations=reservations,
                )
            except Exception as exc:
                commit_error = exc
            assert commit_error is not None, f"COMMIT 未产生断连异常；观察到的 SQL 命令：{observed_queries}"

        assert any(query.strip().upper() == "COMMIT" for query in observed_queries), (
            f"TCP 代理未观察到独立 COMMIT 命令：{observed_queries}"
        )
        assert ack_dropped.is_set(), "TCP 代理未捕获并丢弃 COMMIT 对应的 MySQL OK(0x00) 包"
        assert rolled_back == [], "COMMIT 结果未知时不得回退 Redis Cap reservation"
        assert finalized == [], "连接断开且无法确认时应保留账本，由恢复 Worker 对账"

        # 使用绕过代理的新连接确认 MySQL 实际已提交；只使用本测试随机数据库。
        async with direct_engine.connect() as connection:
            persisted = await connection.scalar(
                text("SELECT COUNT(*) FROM postback_conversions WHERE id = :id"),
                {"id": conversion_id},
            )
        assert persisted == 1, "MySQL 实际未提交，无法证明 COMMIT ACK 丢失场景"
    finally:
        if proxy_server is not None:
            proxy_server.close()
            await proxy_server.wait_closed()
        if proxy_engine is not None:
            await proxy_engine.dispose()
        if direct_engine is not None:
            await direct_engine.dispose()
        _drop_isolated_mysql_database(database)


@pytest.mark.asyncio
async def test_redis_rollback_tombstone_makes_retry_idempotent(monkeypatch):
    """真实隔离 Redis 验证：Lua 回滚后保留墓碑，重试绝不二次 DECR。"""
    from app.core.cap import redis_counter as redis_counter_module

    client = Redis.from_url(REDIS_URL, decode_responses=True)
    suffix = uuid.uuid4().hex
    counter_key = f"ci:cap:rollback:{suffix}"
    token_key = f"{counter_key}:reservation:{suffix}"

    async def get_client():
        return client

    monkeypatch.setattr(redis_counter_module, "get_redis_client", get_client)
    try:
        await client.set(counter_key, 1)
        await client.set(token_key, "1")

        first = await client.eval(
            RedisCapManager._ROLLBACK_RESERVATION_LUA,
            2,
            counter_key,
            token_key,
        )
        assert first == 0
        assert await client.get(counter_key) == "0"
        assert await client.get(token_key) == "ROLLED_BACK"

        # 模拟 Redis 已完成回滚、MySQL 尚未 ACK 时进程崩溃后再次执行。
        second = await RedisCapManager.rollback_reservation_keys(counter_key, token_key)
        assert second == 0
        assert await client.get(counter_key) == "0"
        assert await RedisCapManager.get_reservation_token_state(
            counter_key, token_key
        ) == "ROLLED_BACK"
    finally:
        await client.delete(counter_key, token_key)
        await client.aclose()


@pytest.mark.asyncio
async def test_mysql_recovery_lease_uses_database_clock_when_worker_clock_is_ahead(monkeypatch):
    """Worker 本机时钟超前时，不得提前接管另一请求尚未到期的租约。"""
    from datetime import datetime

    database = _create_isolated_mysql_database()
    engine = None
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

        row, claimed, owner = await CapReservationLedger.prepare_and_claim(
            platform="ci-clock-skew",
            conversion_id=f"clock-skew-{uuid.uuid4().hex}",
            event_name="purchase",
            offer_id=int(uuid.uuid4().int % 900_000_000) + 100_000_000,
            publisher_id=None,
            cap_kind="total",
            business_date=None,
        )
        assert claimed is True
        assert owner

        # 从 MySQL 读取基准时间，再模拟恢复 Worker 本机时钟超前 6 小时。
        async with session_factory() as session:
            database_now = await session.scalar(text("SELECT NOW()"))
        worker_clock_ahead = database_now + timedelta(hours=6)
        monkeypatch.setattr(
            recovery_module,
            "get_app_now_naive",
            lambda: worker_clock_ahead,
        )

        stats = await recovery_module.recover_cap_reservations(batch_size=10)

        async with session_factory() as session:
            persisted = await session.scalar(
                select(CapReservation).where(
                    CapReservation.reservation_key == row.reservation_key
                )
            )

        assert stats["claimed"] == 0
        assert stats["rolled_back"] == 0
        assert persisted.state == "PREPARED"
        assert persisted.lease_owner == owner
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_mysql_database(database)
