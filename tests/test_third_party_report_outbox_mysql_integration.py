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
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import third_party_report as report_module
from app.core.utils import get_app_now_naive
from app.models.third_party import ThirdPartyReportLog, ThirdPartyReportIdentityLock
from app.models.postback import PostbackForwardLog
from app.services import third_party_report_pii_retention as retention_module
from app.services import third_party_report_outbox as outbox_module
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

        now = get_app_now_naive().replace(microsecond=0)
        # MySQL DATETIME 使用秒级精度；可控时钟也统一截断微秒，避免测试精度不一致。
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
                platform="meta",
                identity_scope="platform_scoped",
                destination_pixel_id="pixel-ci",
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
            report_module._claim_report_log(report_id, expected_scope="platform_scoped", platform="meta"),
            report_module._claim_report_log(report_id, expected_scope="platform_scoped", platform="meta"),
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
        new_token = await report_module._claim_report_log(report_id, expected_scope="platform_scoped", platform="meta")
        assert new_token is not None
        assert new_token != first_token

        # MySQL DATETIME 秒级精度：同一秒立即续租应确认当前租约仍有效，
        # 不应因 UPDATE 未改变字段值而被 changed-rows rowcount 误判为失租。
        same_second_renewal = await report_module._renew_report_log_lease(
            report_id, new_token, expected_scope="platform_scoped", platform="meta"
        )
        assert same_second_renewal == new_token

        stale_update = await report_module.update_report_log(
            report_id,
            status="failed",
            expected_report_start_time=first_token,
            expected_identity_scope="platform_scoped",
            expected_platform="meta",
        )
        assert stale_update is False

        current_update = await report_module.update_report_log(
            report_id,
            status="failed",
            expected_report_start_time=new_token,
            expected_identity_scope="platform_scoped",
            expected_platform="meta",
        )
        assert current_update is True

        # 当前 Worker 只能在原租约仍有效时续租，续租后旧令牌立即失效。
        lease_clock[0] += timedelta(seconds=5)
        renewed_token = await report_module._renew_report_log_lease(
            report_id, new_token, expected_scope="platform_scoped", platform="meta"
        )
        assert renewed_token == lease_clock[0]
        stale_renewal = await report_module._renew_report_log_lease(
            report_id, new_token, expected_scope="platform_scoped", platform="meta"
        )
        assert stale_renewal is None

        # 超过 TTL 后，旧 Worker 不得复活租约；新 Worker 可以接管。
        lease_clock[0] += timedelta(seconds=report_module.REPORT_LOG_LEASE_SECONDS + 1)
        expired_renewal = await report_module._renew_report_log_lease(
            report_id, renewed_token, expected_scope="platform_scoped", platform="meta"
        )
        assert expired_renewal is None
        replacement_token = await report_module._claim_report_log(report_id, expected_scope="platform_scoped", platform="meta")
        assert replacement_token == lease_clock[0]
        assert replacement_token != renewed_token
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
async def test_mysql_schema_bootstrap_creates_orm_tables_and_checks_table_column_presence(monkeypatch):
    """真实 MySQL 验证启动建表锁及 ORM 表/列存在性（不代表完整元数据比对）。"""
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

@pytest.mark.asyncio
async def test_mysql_outbox_stale_worker_cannot_renew_or_finalize_after_takeover(monkeypatch):
    """A Worker 暂停超过 TTL 后，B 接管；A 恢复不得续租或覆盖 B 的状态。"""
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

        # 使用 MySQL DATETIME 秒级精度的可控时钟模拟 A 暂停及 B 接管。
        lease_clock = [get_app_now_naive().replace(microsecond=0)]
        monkeypatch.setattr(report_module, "get_app_now_naive", lambda: lease_clock[0])
        event_identity = uuid.uuid4().hex
        async with session_factory() as session:
            row = ThirdPartyReportLog(
                source="ci",
                adsid=f"ci-outbox-stale-worker-{event_identity}",
                event="Purchase",
                event_key=hashlib.sha256(event_identity.encode("utf-8")).hexdigest(),
                platform="meta",
                identity_scope="platform_scoped",
                destination_pixel_id="pixel-ci",
                conversion_id=event_identity,
                status="pending",
                outbox_enqueued=True,
                attempt_count=0,
                max_attempts=5,
                next_retry_time=lease_clock[0] - timedelta(minutes=1),
                report_start_time=None,
            )
            session.add(row)
            await session.commit()
            report_id = row.id

        # Worker A 取得租约后暂停；暂停时间超过租约 TTL。
        worker_a_token = await report_module._claim_report_log(report_id, expected_scope="platform_scoped", platform="meta")
        assert worker_a_token == lease_clock[0]
        lease_clock[0] += timedelta(seconds=report_module.REPORT_LOG_LEASE_SECONDS + 1)

        # Worker B 接管同一条记录，A 的令牌从此失效。
        worker_b_token = await report_module._claim_report_log(report_id, expected_scope="platform_scoped", platform="meta")
        assert worker_b_token == lease_clock[0]
        assert worker_b_token != worker_a_token

        # A 恢复后，发送前续租检查必须失败；不能进入 HTTP 发送路径。
        stale_worker_renewal = await report_module._renew_report_log_lease(
            report_id, worker_a_token, expected_scope="platform_scoped", platform="meta"
        )
        assert stale_worker_renewal is None

        # A 也不能把 B 正在处理的记录写成 failed/success。
        stale_worker_finalize = await report_module.update_report_log(
            report_id,
            status="failed",
            expected_report_start_time=worker_a_token,
            expected_identity_scope="platform_scoped",
            expected_platform="meta",
        )
        assert stale_worker_finalize is False

        # B 仍持有有效令牌，可以完成状态确认。
        worker_b_finalize = await report_module.update_report_log(
            report_id,
            status="success",
            expected_report_start_time=worker_b_token,
            expected_identity_scope="platform_scoped",
            expected_platform="meta",
        )
        assert worker_b_finalize is True

        async with session_factory() as session:
            final_row = await session.scalar(
                select(ThirdPartyReportLog).where(ThirdPartyReportLog.id == report_id)
            )
            assert final_row is not None
            assert final_row.status == "success"
            assert final_row.report_start_time == worker_b_token
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "adsid", "event", "conversion_id", "platform"),
    [
        ("postback", "ascii-click:001", "Purchase", "conv-001", None),
        ("postback", "中文点击-001", "Purchase", "转化-甲", None),
        ("postback", "emoji-😀-click", "Purchase", "订单-😀", "bft"),
        ("postback", "含冒号:和长度", "ViewContent", "后补-转化ID", "平台-甲"),
        ("短链", "空字段边界", "Purchase", "", "platform-x"),
        ("postback", "blank-platform", "Purchase", "conv-blank", ""),
        ("postback", "whitespace-platform", "Purchase", "conv-space", "   "),
        ("postback", "trim-platform", "Purchase", "conv-trim", " bft "),
    ],
)
async def test_mysql_event_idempotency_golden_vectors_match_python_utf8(
    source, adsid, event, conversion_id, platform
):
    """MySQL SHA2/CHAR_LENGTH 与 Python UTF-8 长度前缀算法对 Unicode 字节级一致。"""
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
        parts = [
            ("source", source),
            ("adsid", adsid),
            ("event", event),
            (
                "conversion_id",
                "" if event == "ViewContent" else (conversion_id or ""),
            ),
        ]
        normalized_platform = (platform or "").strip()
        if normalized_platform:
            parts.append(("platform", normalized_platform))

        concat_args = []
        params = {}
        for name, value in parts:
            params[name] = value
            concat_args.extend([f"CHAR_LENGTH(:{name})", "':'", f":{name}"])
        sql = "SELECT SHA2(CONCAT(" + ", ".join(concat_args) + "), 256)"
        async with engine.connect() as connection:
            mysql_key = await connection.scalar(text(sql), params)

        python_key = report_module.build_event_idempotency_key(
            source, adsid, event, conversion_id, platform=platform
        )
        assert mysql_key == python_key
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_existing_outbox_report_binding_matches_persisted_payload_and_lease(monkeypatch):
    """真实 MySQL 验证 report_log_id 只能绑定同一持久化载荷和当前租约。"""
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

        now = get_app_now_naive().replace(microsecond=0)
        event_identity = uuid.uuid4().hex
        event_key = hashlib.sha256(event_identity.encode("utf-8")).hexdigest()
        async with session_factory() as session:
            row = ThirdPartyReportLog(
                source="postback",
                adsid=f"ci-binding-{event_identity}",
                event="Purchase",
                event_key=event_key,
                platform="meta",
                identity_scope="platform_scoped",
                destination_pixel_id="pixel-ci",
                conversion_id=f"conversion-{event_identity}",
                status="pending",
                outbox_enqueued=True,
                attempt_count=0,
                max_attempts=5,
                next_retry_time=now,
                report_start_time=now,
            )
            session.add(row)
            await session.commit()
            report_id = row.id

        valid = await report_module._validate_existing_report_log_binding(
            report_id,
            source="postback",
            adsid=f"ci-binding-{event_identity}",
            event="Purchase",
            conversion_id=f"conversion-{event_identity}",
            event_key=event_key,
            platform="meta",
            destination_pixel_id="pixel-ci",
            lease_token=now,
        )
        wrong_adsid = await report_module._validate_existing_report_log_binding(
            report_id,
            source="postback",
            adsid="different-click-id",
            event="Purchase",
            conversion_id=f"conversion-{event_identity}",
            event_key=event_key,
            platform="meta",
            destination_pixel_id="pixel-ci",
            lease_token=now,
        )
        stale_lease = await report_module._validate_existing_report_log_binding(
            report_id,
            source="postback",
            adsid=f"ci-binding-{event_identity}",
            event="Purchase",
            conversion_id=f"conversion-{event_identity}",
            event_key=event_key,
            platform="meta",
            destination_pixel_id="pixel-ci",
            lease_token=now - timedelta(seconds=1),
        )

        assert valid is True
        assert wrong_adsid is False
        assert stale_lease is False
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_outbox_pixel_destination_is_bound_once_and_cannot_silently_change(monkeypatch):
    """真实 MySQL 验证 Outbox 首次 Pixel 绑定可重复确认，但不可改投另一个 Pixel。"""
    from app.services import third_party_report_outbox as outbox_module

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
        monkeypatch.setattr(outbox_module, "AsyncSessionLocal", session_factory)
        lease = get_app_now_naive().replace(microsecond=0)
        identity = uuid.uuid4().hex
        async with session_factory() as session:
            row = ThirdPartyReportLog(
                source="postback",
                adsid=f"pixel-bind-{identity}",
                event="Purchase",
                event_key=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                platform="meta",
                identity_scope="platform_scoped",
                destination_pixel_id=None,
                conversion_id=f"conversion-{identity}",
                status="pending",
                outbox_enqueued=True,
                attempt_count=0,
                max_attempts=5,
                next_retry_time=lease,
                report_start_time=lease,
            )
            session.add(row)
            await session.commit()
            report_id = row.id

        first_bind = await outbox_module._bind_outbox_destination(
            report_id,
            lease_token=lease,
            platform="meta",
            pixel_id="pixel-A",
        )
        same_pixel_retry = await outbox_module._bind_outbox_destination(
            report_id,
            lease_token=lease,
            platform="meta",
            pixel_id="pixel-A",
        )
        changed_pixel = await outbox_module._bind_outbox_destination(
            report_id,
            lease_token=lease,
            platform="meta",
            pixel_id="pixel-B",
        )

        assert first_bind is True
        assert same_pixel_retry is True
        assert changed_pixel is False

        async with session_factory() as session:
            persisted = await session.get(ThirdPartyReportLog, report_id)
            assert persisted.destination_pixel_id == "pixel-A"
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_direct_and_postback_creation_share_one_base_identity_lock(monkeypatch):
    """真实 MySQL 并发验证直接发送与 Postback 首次创建只能有一个身份所有者。"""
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
            await connection.run_sync(ThirdPartyReportIdentityLock.__table__.create)

        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        monkeypatch.setattr(report_module, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(outbox_module, "AsyncSessionLocal", session_factory)

        identity = uuid.uuid4().hex
        adsid = f"cross-path-{identity}"
        conversion_id = f"conversion-{identity}"

        async def direct_create():
            return await report_module.create_report_log(
                source="postback",
                adsid=adsid,
                event="Purchase",
                email="",
                ip="",
                phone="",
                ua="",
                conversion_id=conversion_id,
                destination_pixel_id="pixel-direct",
            )

        async def postback_create(platform="meta"):
            async with session_factory() as session:
                async with session.begin():
                    return await outbox_module.enqueue_postback_report(
                        session,
                        platform=platform,
                        adsid=adsid,
                        event="Purchase",
                        conversion_id=conversion_id,
                        email=None,
                        ip=None,
                        phone=None,
                        ua=None,
                        currency="USD",
                        amount=12.0,
                        short_link_id=7,
                        cloak_name=None,
                        short_code=None,
                        click_time=None,
                    )

        outcomes = await asyncio.gather(
            direct_create(),
            postback_create(),
            return_exceptions=True,
        )
        successful_ids = [
            value for value in outcomes
            if isinstance(value, int) and value > 0
        ]
        conflicts = [
            value for value in outcomes
            if isinstance(value, outbox_module.LegacyEventIdentityConflict)
        ]
        assert len(successful_ids) == 1
        assert len(conflicts) + sum(value == 0 for value in outcomes) == 1

        async with session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(ThirdPartyReportLog).where(
                            ThirdPartyReportLog.adsid == adsid
                        )
                    )
                ).scalars().all()
            )
            locks = list(
                (
                    await session.execute(
                        select(ThirdPartyReportIdentityLock).where(
                            ThirdPartyReportIdentityLock.identity_key
                            == report_module.build_event_idempotency_key(
                                "postback", adsid, "Purchase", conversion_id
                            )
                        )
                    )
                ).scalars().all()
            )
            assert len(rows) == 1
            assert len(locks) == 1
            assert rows[0].identity_scope in {"unscoped", "platform_scoped"}

        # 同一基础身份下明确平台 A/B 可以并存；同平台重复 Postback 复用原行。
        multi_adsid = f"multi-platform-{uuid.uuid4().hex}"
        multi_conversion = f"multi-conversion-{uuid.uuid4().hex}"

        async def create_platform(platform):
            async with session_factory() as session:
                async with session.begin():
                    return await outbox_module.enqueue_postback_report(
                        session,
                        platform=platform,
                        adsid=multi_adsid,
                        event="Purchase",
                        conversion_id=multi_conversion,
                        email=None,
                        ip=None,
                        phone=None,
                        ua=None,
                        currency="USD",
                        amount=2.0,
                        short_link_id=8,
                        cloak_name=None,
                        short_code=None,
                        click_time=None,
                    )

        platform_ids = await asyncio.gather(
            create_platform("meta"),
            create_platform("bft"),
        )
        repeated_meta = await create_platform("meta")
        assert len(set(platform_ids)) == 2
        assert repeated_meta == platform_ids[0]

        async with session_factory() as session:
            scoped_rows = list(
                (
                    await session.execute(
                        select(ThirdPartyReportLog).where(
                            ThirdPartyReportLog.adsid == multi_adsid
                        )
                    )
                ).scalars().all()
            )
            assert {row.platform for row in scoped_rows} == {"meta", "bft"}
            assert {row.identity_scope for row in scoped_rows} == {"platform_scoped"}
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_identity_lock_rollback_releases_row_and_hash_collision_fails_closed(monkeypatch):
    """真实 MySQL 验证事务回滚释放首次锁行，并拒绝 SHA-256 键对应不同原文。"""
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
            await connection.run_sync(ThirdPartyReportIdentityLock.__table__.create)

        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        monkeypatch.setattr(report_module, "AsyncSessionLocal", session_factory)

        rollback_identity = (
            "postback",
            f"rollback-{uuid.uuid4().hex}",
            "Purchase",
            f"conversion-{uuid.uuid4().hex}",
        )
        rollback_key = report_module.build_event_idempotency_key(*rollback_identity)
        async with session_factory() as session:
            with pytest.raises(RuntimeError, match="synthetic rollback"):
                async with session.begin():
                    await report_module._lock_report_base_identity(
                        session,
                        source=rollback_identity[0],
                        adsid=rollback_identity[1],
                        event=rollback_identity[2],
                        conversion_id=rollback_identity[3],
                    )
                    raise RuntimeError("synthetic rollback")

        async with session_factory() as session:
            missing = await session.get(ThirdPartyReportIdentityLock, rollback_key)
            assert missing is None

        async with session_factory() as session:
            async with session.begin():
                reacquired = await report_module._lock_report_base_identity(
                    session,
                    source=rollback_identity[0],
                    adsid=rollback_identity[1],
                    event=rollback_identity[2],
                    conversion_id=rollback_identity[3],
                )
                assert reacquired == rollback_key

        collision_identity = (
            "postback",
            f"collision-{uuid.uuid4().hex}",
            "Purchase",
            f"conversion-{uuid.uuid4().hex}",
        )
        collision_key = report_module.build_event_idempotency_key(*collision_identity)
        async with session_factory() as session:
            session.add(
                ThirdPartyReportIdentityLock(
                    identity_key=collision_key,
                    identity_value=b"not-the-canonical-identity",
                )
            )
            await session.commit()

        async with session_factory() as session:
            with pytest.raises(RuntimeError, match="SHA-256"):
                async with session.begin():
                    await report_module._lock_report_base_identity(
                        session,
                        source=collision_identity[0],
                        adsid=collision_identity[1],
                        event=collision_identity[2],
                        conversion_id=collision_identity[3],
                    )
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_identity_lock_wait_timeout_fails_closed_and_can_retry(monkeypatch):
    """真实 MySQL 验证身份锁等待有上限，超时失败后释放事务可安全重试。"""
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
            await connection.run_sync(ThirdPartyReportIdentityLock.__table__.create)

        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        monkeypatch.setattr(report_module, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(report_module, "REPORT_IDENTITY_LOCK_WAIT_SECONDS", 1)
        identity = (
            "postback",
            f"lock-timeout-{uuid.uuid4().hex}",
            "Purchase",
            f"conversion-{uuid.uuid4().hex}",
        )

        async with session_factory() as first, session_factory() as second:
            async with first.begin():
                await report_module._lock_report_base_identity(
                    first,
                    source=identity[0],
                    adsid=identity[1],
                    event=identity[2],
                    conversion_id=identity[3],
                )
                with pytest.raises(OperationalError):
                    async with second.begin():
                        await report_module._lock_report_base_identity(
                            second,
                            source=identity[0],
                            adsid=identity[1],
                            event=identity[2],
                            conversion_id=identity[3],
                        )

            # 第一事务提交释放锁后，第二连接应能重新取得同一身份锁。
            async with second.begin():
                key = await report_module._lock_report_base_identity(
                    second,
                    source=identity[0],
                    adsid=identity[1],
                    event=identity[2],
                    conversion_id=identity[3],
                )
                assert key == report_module.build_event_idempotency_key(*identity)
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)
