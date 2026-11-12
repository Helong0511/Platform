"""第三方 Report Outbox 的真实 MySQL 并发认领集成测试。

仅连接 CI 显式提供的本机临时 MySQL platform_ci；禁止访问远程/生产数据库。
"""
import asyncio
import hashlib
import ipaddress
import os
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from urllib.parse import quote_plus

import pymysql
import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import third_party_report as report_module
from app.core.utils import get_app_now_naive
from app.models.third_party import ThirdPartyReportLog
from app.models.postback import PostbackForwardLog
from app.services import third_party_report_pii_retention as retention_module
from app.bootstrap import lifespan as lifespan_module


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

# CI 显式启用集成测试却配置了非隔离目标时必须失败关闭。
if (
    os.getenv("GITHUB_ACTIONS") == "true"
    or (os.getenv("UNIT_TEST") == "1" and MYSQL_HOST)
) and not _SAFE_MYSQL_TARGET:
    raise RuntimeError(
        "拒绝执行 Outbox MySQL 集成测试：必须使用 loopback MySQL platform_ci，"
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
        autocommit=True,
        charset="utf8mb4",
    )


def _create_isolated_database() -> str:
    database = f"platform_ci_outbox_{uuid.uuid4().hex[:16]}"
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


def _drop_isolated_database(database: str) -> None:
    # database 由 UUID 生成，不接受外部输入。
    connection = _admin_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_mysql_outbox_claim_is_exclusive_and_expired_lease_is_recoverable(monkeypatch):
    """两个 Worker 同时认领同一条 Outbox 时只能有一个成功，过期后可重新认领。"""
    database = _create_isolated_database()
    engine = None
    try:
        password = quote_plus(MYSQL_PASSWORD)
        user = quote_plus(MYSQL_USER)
        engine = create_async_engine(
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}"
            "?charset=utf8mb4",
            pool_pre_ping=True,
        )
        async with engine.begin() as connection:
            await connection.run_sync(ThirdPartyReportLog.__table__.create)

        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        monkeypatch.setattr(report_module, "AsyncSessionLocal", session_factory)

        now = get_app_now_naive()
        # 使用可控时钟推进租约令牌，避免依赖真实 sleep 或调度精度。
        lease_clock = [now]
        monkeypatch.setattr(report_module, "get_app_now_naive", lambda: lease_clock[0])
        event_identity = uuid.uuid4().hex
        event_key = hashlib.sha256(event_identity.encode("utf-8")).hexdigest()
        async with session_factory() as session:
            row = ThirdPartyReportLog(
                source="ci",
                adsid=f"ci-outbox-{event_identity}",
                event="Purchase",
                event_key=event_key,
                conversion_id=event_identity,
                status="pending",
                outbox_enqueued=True,
                attempt_count=0,
                max_attempts=5,
                next_retry_time=now - timedelta(minutes=1),
                report_start_time=None,
            )
            session.add(row)
            await session.commit()
            report_id = row.id

        claims = await asyncio.gather(
            report_module._claim_report_log(report_id),
            report_module._claim_report_log(report_id),
        )
        assert sum(token is not None for token in claims) == 1
        assert all(token is None or isinstance(token, datetime) for token in claims)

        async with session_factory() as session:
            claimed_row = await session.scalar(
                select(ThirdPartyReportLog).where(ThirdPartyReportLog.id == report_id)
            )
            assert claimed_row is not None
            assert claimed_row.report_start_time is not None

            # 模拟 Worker 崩溃：租约过期后，同一事件允许另一个 Worker 接管。
            await session.execute(
                update(ThirdPartyReportLog)
                .where(ThirdPartyReportLog.id == report_id)
                .values(
                    report_start_time=lease_clock[0] - timedelta(minutes=6),
                    next_retry_time=lease_clock[0] - timedelta(minutes=1),
                )
            )
            await session.commit()

        # 过期租约只能由新 Worker 接管；旧 Worker 的租约令牌不能再修改状态。
        first_token = next(token for token in claims if token is not None)
        lease_clock[0] += timedelta(seconds=1)
        new_token = await report_module._claim_report_log(report_id)
        assert new_token is not None
        assert new_token != first_token

        stale_update = await report_module.update_report_log(
            report_id,
            status="failed",
            expected_report_start_time=first_token,
        )
        assert stale_update is False

        current_update = await report_module.update_report_log(
            report_id,
            status="failed",
            expected_report_start_time=new_token,
        )
        assert current_update is True
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_pii_retention_preserves_active_leases_and_exact_forward_targets(monkeypatch):
    """真实 MySQL 验证 PII 清理的租约保护、队列目标匹配和 NULL-safe 语义。"""
    database = _create_isolated_database()
    engine = None
    try:
        password = quote_plus(MYSQL_PASSWORD)
        user = quote_plus(MYSQL_USER)
        engine = create_async_engine(
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}"
            "?charset=utf8mb4",
            pool_pre_ping=True,
        )
        async with engine.begin() as connection:
            await connection.run_sync(ThirdPartyReportLog.__table__.create)
            await connection.execute(text(
                "CREATE TABLE postback_forward_logs ("
                "id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
                "conversion_id INT NOT NULL, product_id INT NULL, publisher_id INT NULL, "
                "downstream_url VARCHAR(500) NOT NULL, request_method VARCHAR(10) NOT NULL, "
                "request_data TEXT NULL, request_params TEXT NULL, response_status INT NULL, "
                "response_body TEXT NULL, success TINYINT(1) NOT NULL DEFAULT 0, "
                "error_message TEXT NULL, retry_count INT NOT NULL DEFAULT 0, "
                "created_at DATETIME NOT NULL, completed_at DATETIME NULL, "
                "pii_scrubbed_at DATETIME NULL"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            ))
            # 清理查询只读取队列表的 id/目标列；本隔离表故意不建立外键。
            await connection.execute(text(
                "CREATE TABLE postback_forward_queue ("
                "id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
                "conversion_id INT NOT NULL, product_id INT NULL, publisher_id INT NULL"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            ))

        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        now = get_app_now_naive()
        cutoff_time = now - timedelta(days=120)
        monkeypatch.setattr(retention_module, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(retention_module, "get_app_now_naive", lambda: now)

        scrub_key = hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest()
        lease_key = hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest()
        retry_key = hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest()

        async with session_factory() as session:
            session.add_all([
                ThirdPartyReportLog(
                    source="ci", adsid="ci-pii-terminal", event="Purchase",
                    event_key=scrub_key, status="success", created_at=cutoff_time,
                    email="terminal@example.invalid", ip="203.0.113.20",
                    phone="4155550120", ua="terminal-agent",
                    report_params='{"email":"terminal@example.invalid"}',
                    response_body='{"echo":"terminal@example.invalid"}',
                    log_id="terminal-log-id", report_start_time=None,
                    outbox_enqueued=False,
                ),
                ThirdPartyReportLog(
                    source="ci", adsid="ci-pii-active-lease", event="Purchase",
                    event_key=lease_key, status="success", created_at=cutoff_time,
                    email="lease@example.invalid", report_start_time=now - timedelta(seconds=60),
                    outbox_enqueued=False,
                ),
                ThirdPartyReportLog(
                    source="ci", adsid="ci-pii-active-retry", event="Purchase",
                    event_key=retry_key, status="failed", created_at=cutoff_time,
                    email="retry@example.invalid", report_start_time=None,
                    outbox_enqueued=True, attempt_count=0, max_attempts=5,
                    next_retry_time=now + timedelta(minutes=5),
                    short_link_id=901, cloak_name="ci-cloak", short_code="ci-short",
                ),
            ])
            session.add_all([
                PostbackForwardLog(
                    conversion_id=700, publisher_id=11, product_id=21,
                    downstream_url="https://partner.invalid/a?email=a@example.invalid",
                    request_method="POST", request_params='{"email":"a@example.invalid"}',
                    response_body='{"echo":"a@example.invalid"}',
                    created_at=cutoff_time, completed_at=cutoff_time,
                ),
                PostbackForwardLog(
                    conversion_id=701, publisher_id=11, product_id=21,
                    downstream_url="https://partner.invalid/b?email=b@example.invalid",
                    request_method="POST", request_params='{"email":"b@example.invalid"}',
                    response_body='{"echo":"b@example.invalid"}',
                    created_at=cutoff_time, completed_at=cutoff_time,
                ),
                PostbackForwardLog(
                    conversion_id=702, publisher_id=None, product_id=None,
                    downstream_url="https://partner.invalid/c?email=c@example.invalid",
                    request_method="POST", request_params='{"email":"c@example.invalid"}',
                    response_body='{"echo":"c@example.invalid"}',
                    created_at=cutoff_time, completed_at=cutoff_time,
                ),
                PostbackForwardLog(
                    conversion_id=703, publisher_id=None, product_id=21,
                    downstream_url="https://partner.invalid/d?email=d@example.invalid",
                    request_method="POST", request_params='{"email":"d@example.invalid"}',
                    response_body='{"echo":"d@example.invalid"}',
                    created_at=cutoff_time, completed_at=cutoff_time,
                ),
            ])
            await session.commit()

        async with engine.begin() as connection:
            await connection.execute(text(
                "INSERT INTO postback_forward_queue "
                "(conversion_id, publisher_id, product_id) VALUES "
                "(700, 11, 21), "       # 完全匹配：必须保留
                "(701, 99, 22), "       # 同 conversion、不同目标：不得阻塞清理
                "(702, NULL, NULL), "   # NULL/NULL 目标完全匹配：必须保留
                "(703, 11, 21)"          # publisher 不匹配：不得阻塞清理
            ))

        result = await retention_module.scrub_expired_third_party_report_pii(
            retention_days=90,
            batch_size=200,
        )
        assert result["third_party_report_logs_scrubbed"] == 1
        assert result["postback_forward_logs_scrubbed"] == 2

        async with session_factory() as session:
            scrubbed_report = await session.scalar(
                select(ThirdPartyReportLog).where(ThirdPartyReportLog.event_key == scrub_key)
            )
            active_lease_report = await session.scalar(
                select(ThirdPartyReportLog).where(ThirdPartyReportLog.event_key == lease_key)
            )
            active_retry_report = await session.scalar(
                select(ThirdPartyReportLog).where(ThirdPartyReportLog.event_key == retry_key)
            )
            assert scrubbed_report is not None
            assert scrubbed_report.pii_scrubbed_at is not None
            assert scrubbed_report.event_key == scrub_key
            assert scrubbed_report.adsid == ""
            assert scrubbed_report.conversion_id is None
            assert scrubbed_report.email is None
            assert scrubbed_report.report_params is None
            assert active_lease_report.email == "lease@example.invalid"
            assert active_lease_report.pii_scrubbed_at is None
            assert active_retry_report.email == "retry@example.invalid"
            assert active_retry_report.pii_scrubbed_at is None

            forward_rows = (
                await session.execute(
                    select(PostbackForwardLog).order_by(PostbackForwardLog.conversion_id)
                )
            ).scalars().all()
            by_conversion = {row.conversion_id: row for row in forward_rows}
            assert by_conversion[700].pii_scrubbed_at is None
            assert by_conversion[700].request_params is not None
            assert by_conversion[701].pii_scrubbed_at is not None
            assert by_conversion[701].request_params is None
            assert by_conversion[701].downstream_url == "[已按保留策略清除]"
            assert by_conversion[702].pii_scrubbed_at is None
            assert by_conversion[702].request_params is not None
            assert by_conversion[703].pii_scrubbed_at is not None
            assert by_conversion[703].request_params is None
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_schema_bootstrap_serializes_workers_and_verifies_full_metadata(monkeypatch):
    """真实 MySQL 验证启动建表锁可串行化多 worker，并核对所有 ORM 表/列。"""
    database = _create_isolated_database()
    engine = None
    try:
        password = quote_plus(MYSQL_PASSWORD)
        user = quote_plus(MYSQL_USER)
        engine = create_async_engine(
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}"
            "?charset=utf8mb4",
            pool_pre_ping=True,
        )
        monkeypatch.setattr(lifespan_module, "engine", engine)

        # 完整 ORM metadata 的首次建表与逐表核验。
        await lifespan_module._bootstrap_database_schema()

        async with engine.connect() as connection:
            drift = await connection.run_sync(lifespan_module._schema_metadata_drift)
        assert drift == {"missing_tables": [], "missing_columns": {}}
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_schema_bootstrap_serializes_concurrent_workers(monkeypatch):
    """小型真实 MySQL schema 上验证两个 worker 的 advisory lock 不会死锁。"""
    database = _create_isolated_database()
    engine = None
    try:
        password = quote_plus(MYSQL_PASSWORD)
        user = quote_plus(MYSQL_USER)
        engine = create_async_engine(
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}"
            "?charset=utf8mb4",
            pool_pre_ping=True,
        )
        metadata = MetaData()
        Table(
            "bootstrap_concurrency_probe",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("required_value", String(40), nullable=False),
        )
        monkeypatch.setattr(lifespan_module, "engine", engine)
        monkeypatch.setattr(lifespan_module, "Base", SimpleNamespace(metadata=metadata))

        await asyncio.wait_for(
            asyncio.gather(
                lifespan_module._bootstrap_database_schema(),
                lifespan_module._bootstrap_database_schema(),
            ),
            timeout=20,
        )
        async with engine.connect() as connection:
            drift = await connection.run_sync(
                lambda sync_connection: lifespan_module._schema_metadata_drift(
                    sync_connection, metadata
                )
            )
        assert drift == {"missing_tables": [], "missing_columns": {}}
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_schema_bootstrap_fails_closed_on_missing_column_and_releases_lock(monkeypatch):
    """create_all 不会修补既有表缺列；启动核验必须拒绝并在失败后释放 advisory lock。"""
    database = _create_isolated_database()
    engine = None
    try:
        password = quote_plus(MYSQL_PASSWORD)
        user = quote_plus(MYSQL_USER)
        engine = create_async_engine(
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}"
            "?charset=utf8mb4",
            pool_pre_ping=True,
        )
        metadata = MetaData()
        Table(
            "bootstrap_probe",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("required_value", String(40), nullable=False),
        )
        monkeypatch.setattr(lifespan_module, "engine", engine)
        monkeypatch.setattr(lifespan_module, "Base", SimpleNamespace(metadata=metadata))

        async with engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE bootstrap_probe (id INT NOT NULL PRIMARY KEY) ENGINE=InnoDB")
            )

        with pytest.raises(RuntimeError, match="required_value"):
            await lifespan_module._bootstrap_database_schema()

        # 修复缺列后再次启动成功，证明失败路径已释放 session advisory lock。
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "ALTER TABLE bootstrap_probe "
                    "ADD COLUMN required_value VARCHAR(40) NOT NULL DEFAULT ''"
                )
            )
        await lifespan_module._bootstrap_database_schema()

        async with engine.connect() as connection:
            drift = await connection.run_sync(
                lambda sync_connection: lifespan_module._schema_metadata_drift(
                    sync_connection, metadata
                )
            )
        assert drift == {"missing_tables": [], "missing_columns": {}}
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)
