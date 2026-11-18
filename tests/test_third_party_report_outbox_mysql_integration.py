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
    # 集成测试的管理连接必须有网络超时，避免 DROP DATABASE 在 CI 中无限等待。
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        autocommit=True,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=20,
        write_timeout=10,
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
    # DROP DATABASE 可能等待其它连接释放 metadata lock；限制等待时间并输出
    # 当前连接概况，避免 CI 只在 45 分钟总超时后被动取消。
    connection = _admin_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION lock_wait_timeout = 10")
            try:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            except Exception as exc:
                processlist = []
                try:
                    cursor.execute("SHOW FULL PROCESSLIST")
                    processlist = [
                        {
                            "id": row[0],
                            "user": row[1],
                            "db": row[3],
                            "command": row[4],
                            "time": row[5],
                            "state": row[6],
                        }
                        for row in cursor.fetchall()
                        if row[3] == database or row[0] == connection.thread_id()
                    ]
                except Exception:
                    # 保留 DROP 原始异常；诊断查询失败不能覆盖根因。
                    pass
                raise RuntimeError(
                    f"清理隔离 MySQL 数据库失败：database={database}, "
                    f"processlist={processlist}, error_type={type(exc).__name__}"
                ) from exc
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_mysql_platform_identity_column_uses_exact_binary_comparison():
    """真实 MySQL 验证平台身份比较与 Python 字符串精确语义一致。"""
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
            result = await connection.execute(
                text(
                    "SELECT CHARACTER_SET_NAME, COLLATION_NAME "
                    "FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = 'third_party_report_logs' "
                    "AND COLUMN_NAME = 'platform'"
                )
            )
            column = result.mappings().one()
            assert column["CHARACTER_SET_NAME"] == "utf8mb4"
            assert column["COLLATION_NAME"] == "utf8mb4_bin"

        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        inserted = []
        async with session_factory() as session:
            for exact_platform, alternate_platform in (("meta", "META"), ("cafe", "café")):
                token = uuid.uuid4().hex
                row = ThirdPartyReportLog(
                    source="ci",
                    adsid=f"platform-collation-{token}",
                    event="Purchase",
                    event_key=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                    platform=exact_platform,
                    identity_scope="platform_scoped",
                    destination_pixel_id="pixel-ci",
                    conversion_id=token,
                    status="pending",
                    outbox_enqueued=True,
                    attempt_count=0,
                    max_attempts=3,
                )
                session.add(row)
                inserted.append((row, exact_platform, alternate_platform))
            await session.commit()

        async with session_factory() as session:
            for row, exact_platform, alternate_platform in inserted:
                exact_match = await session.scalar(
                    select(ThirdPartyReportLog.id).where(
                        ThirdPartyReportLog.id == row.id,
                        ThirdPartyReportLog.platform == exact_platform,
                    )
                )
                alternate_match = await session.scalar(
                    select(ThirdPartyReportLog.id).where(
                        ThirdPartyReportLog.id == row.id,
                        ThirdPartyReportLog.platform == alternate_platform,
                    )
                )
                assert exact_match == row.id
                assert alternate_match is None
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_outbox_claim_is_exclusive_and_expired_lease_is_recoverable(monkeypatch):
    """数据库统一时钟认领；Worker 本机时钟快慢均不能提前接管有效租约。"""
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

        # 推进的是 SQL 表达式中的数据库时钟，而不是 Worker 本机时钟。
        # 这样测试仍通过 MySQL 执行到期判断，并能确定性跨越 DATETIME 秒级边界。
        db_clock_offset = [0]
        original_db_clock = report_module.get_app_now_sql_expression
        monkeypatch.setattr(
            report_module,
            "get_app_now_sql_expression",
            lambda offset_seconds=0: original_db_clock(
                db_clock_offset[0] + offset_seconds
            ),
        )

        now = get_app_now_naive().replace(microsecond=0)
        lease_token = uuid.uuid4().hex
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

        # Worker A 本机时钟落后一天，不能因此把到期任务误判为未到期。
        monkeypatch.setattr(
            report_module, "get_app_now_naive",
            lambda: now - timedelta(days=1),
        )
        claims = await asyncio.gather(
            report_module._claim_report_log(report_id, expected_scope="platform_scoped", platform="meta"),
            report_module._claim_report_log(report_id, expected_scope="platform_scoped", platform="meta"),
        )
        assert sum(token is not None for token in claims) == 1
        first_token = next(token for token in claims if token is not None)
        assert isinstance(first_token, str) and len(first_token) == 32
        assert set(first_token) <= set("0123456789abcdef")

        async with session_factory() as session:
            claimed_row = await session.scalar(
                select(ThirdPartyReportLog).where(ThirdPartyReportLog.id == report_id)
            )
            assert claimed_row is not None
            assert claimed_row.lease_token == first_token

        # Worker B 本机时钟快一天，也不能提前接管 DB 时钟下仍有效的租约。
        monkeypatch.setattr(
            report_module, "get_app_now_naive",
            lambda: now + timedelta(days=1),
        )
        premature_claim = await report_module._claim_report_log(
            report_id, expected_scope="platform_scoped", platform="meta"
        )
        assert premature_claim is None

        # 同一秒续租允许返回当前 token；判断是否过期仍由数据库时钟完成。
        same_second_renewal = await report_module._renew_report_log_lease(
            report_id, first_token, expected_scope="platform_scoped", platform="meta"
        )
        assert same_second_renewal is not None
        first_token = same_second_renewal

        async with session_factory() as session:
            await session.execute(
                update(ThirdPartyReportLog)
                .where(ThirdPartyReportLog.id == report_id)
                .values(
                    next_retry_time=datetime(2000, 1, 1),
                )
            )
            await session.commit()

        # 让 SQL 数据库时钟前进 31 秒，超过 claim 的最小 30 秒租约窗口。
        db_clock_offset[0] = report_module.REPORT_LOG_LEASE_SECONDS + 1
        replacement_token = await report_module._claim_report_log(
            report_id, expected_scope="platform_scoped", platform="meta"
        )
        assert replacement_token is not None
        assert replacement_token != first_token

        stale_renewal = await report_module._renew_report_log_lease(
            report_id, first_token, expected_scope="platform_scoped", platform="meta"
        )
        assert stale_renewal is None
        stale_update = await report_module.update_report_log(
            report_id,
            status="failed",
            expected_lease_token=first_token,
            expected_identity_scope="platform_scoped",
            expected_platform="meta",
        )
        assert stale_update is False

        current_update = await report_module.update_report_log(
            report_id,
            status="failed",
            expected_lease_token=replacement_token,
            expected_identity_scope="platform_scoped",
            expected_platform="meta",
        )
        assert current_update is True

        # 再推进 SQL 数据库时钟 31 秒，使 replacement token 真正过期。
        db_clock_offset[0] = (report_module.REPORT_LOG_LEASE_SECONDS + 1) * 2

        expired_renewal = await report_module._renew_report_log_lease(
            report_id, replacement_token,
            expected_scope="platform_scoped", platform="meta"
        )
        assert expired_renewal is None
        expired_finalize = await report_module.update_report_log(
            report_id,
            status="failed",
            expected_lease_token=replacement_token,
            expected_identity_scope="platform_scoped",
            expected_platform="meta",
        )
        assert expired_finalize is False
        final_token = await report_module._claim_report_log(
            report_id, expected_scope="platform_scoped", platform="meta"
        )
        assert final_token is not None
        assert final_token != replacement_token
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

        # Worker 本机时钟不参与租约有效期判断；通过 SQL 数据库时钟表达式模拟暂停。
        lease_clock = [get_app_now_naive().replace(microsecond=0)]
        db_clock_offset = [0]
        original_db_clock = report_module.get_app_now_sql_expression
        monkeypatch.setattr(
            report_module,
            "get_app_now_sql_expression",
            lambda offset_seconds=0: original_db_clock(
                db_clock_offset[0] + offset_seconds
            ),
        )
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
        assert worker_a_token is not None
        async with session_factory() as session:
            claimed_row = await session.scalar(
                select(ThirdPartyReportLog).where(ThirdPartyReportLog.id == report_id)
            )
            assert claimed_row is not None
            # 以数据库实际保存值验证认领令牌，不与认领前本机采样时间比较。
            assert claimed_row.lease_token == worker_a_token

        # Worker A 暂停超过租约 TTL：推进 SQL 表达式的数据库时钟，跨过完整租约窗口.
        db_clock_offset[0] = report_module.REPORT_LOG_LEASE_SECONDS + 1

        # Worker B 接管同一条记录，A 的令牌从此失效。
        worker_b_token = await report_module._claim_report_log(report_id, expected_scope="platform_scoped", platform="meta")
        assert worker_b_token is not None
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
            expected_lease_token=worker_a_token,
            expected_identity_scope="platform_scoped",
            expected_platform="meta",
        )
        assert stale_worker_finalize is False

        # B 仍持有有效令牌，可以完成状态确认。
        worker_b_finalize = await report_module.update_report_log(
            report_id,
            status="success",
            expected_lease_token=worker_b_token,
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
            assert final_row.report_start_time is not None
            assert final_row.lease_token is None
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
        lease_token = uuid.uuid4().hex
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
                lease_token=lease_token,
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
            lease_token=lease_token,
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
            lease_token=lease_token,
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
            lease_token='f' * 32,
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
        lease = get_app_now_naive().replace(microsecond=0) - timedelta(seconds=1)
        lease_token = uuid.uuid4().hex
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
                lease_token=lease_token,
            )
            session.add(row)
            await session.commit()
            report_id = row.id

        first_bind = await outbox_module._bind_outbox_destination(
            report_id,
            lease_token=lease_token,
            platform="meta",
            pixel_id="pixel-A",
        )
        same_pixel_retry = await outbox_module._bind_outbox_destination(
            report_id,
            lease_token=lease_token,
            platform="meta",
            pixel_id="pixel-A",
        )
        changed_pixel = await outbox_module._bind_outbox_destination(
            report_id,
            lease_token=lease_token,
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
@pytest.mark.parametrize(
    ("event", "legacy_conversion_id", "new_conversion_id"),
    [
        ("Purchase", "legacy-conversion", "legacy-conversion"),
        ("Purchase", None, ""),
        ("ViewContent", "legacy-conversion", "new-conversion"),
    ],
)
async def test_mysql_unresolved_legacy_platform_key_blocks_new_direct_and_other_platform_events(
    monkeypatch, event, legacy_conversion_id, new_conversion_id
):
    """历史五字段 key 没有 platform 列时，任何新平台/直接发送入口都必须 fail closed。"""
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
        adsid = f"legacy-five-field-{identity}"
        stored_conversion_id = (
            legacy_conversion_id if event != "ViewContent" else legacy_conversion_id
        )
        legacy_key = report_module.build_event_idempotency_key(
            "postback",
            adsid,
            event,
            stored_conversion_id,
            platform="legacy-platform-A",
        )
        now = get_app_now_naive()
        async with session_factory() as session:
            session.add(
                ThirdPartyReportLog(
                    source="postback",
                    adsid=adsid,
                    event=event,
                    event_key=legacy_key,
                    conversion_id=stored_conversion_id,
                    platform=None,
                    identity_scope="legacy_unresolved",
                    destination_pixel_id=None,
                    outbox_enqueued=True,
                    status="failed",
                    attempt_count=1,
                    max_attempts=12,
                    created_at=now,
                    next_retry_time=None,
                )
            )
            await session.commit()

        # 新平台 B 的五字段 key 与历史平台 A 不同，但基础身份相同，必须拒绝。
        async with session_factory() as session:
            with pytest.raises(outbox_module.LegacyEventIdentityConflict):
                async with session.begin():
                    await outbox_module.enqueue_postback_report(
                        session,
                        platform="legacy-platform-B",
                        adsid=adsid,
                        event=event,
                        conversion_id=new_conversion_id,
                        email=None,
                        ip=None,
                        phone=None,
                        ua=None,
                        currency="USD",
                        amount=3.0,
                        short_link_id=9,
                        cloak_name=None,
                        short_code=None,
                        click_time=None,
                    )

        # 无平台直接发送入口也必须检查相同的 unresolved 基础身份，不能绕过 Postback 门禁。
        direct_id = await report_module.create_report_log(
            source="postback",
            adsid=adsid,
            event=event,
            email="",
            ip="",
            phone="",
            ua="",
            conversion_id=new_conversion_id,
            destination_pixel_id="pixel-direct",
        )
        assert direct_id == 0

        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(ThirdPartyReportLog).where(
                        ThirdPartyReportLog.adsid == adsid
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].identity_scope == "legacy_unresolved"
            assert rows[0].event_key == legacy_key
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
                    identity_fingerprint=b"x" * 64,
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
                # 在第二个 session 的同一物理连接/事务中设置 1 秒等待上限。
                await second.execute(text("SET SESSION innodb_lock_wait_timeout = 1"))
                with pytest.raises(OperationalError):
                    await report_module._lock_report_base_identity(
                        second,
                        source=identity[0],
                        adsid=identity[1],
                        event=identity[2],
                        conversion_id=identity[3],
                    )
                await second.rollback()

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


@pytest.mark.asyncio
async def test_mysql_direct_first_and_postback_first_both_reject_cross_scope_duplicates(monkeypatch):
    """真实 MySQL 覆盖两种创建先后顺序，证明无平台与平台事件不能并存。"""
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

        async def direct(adsid, conversion_id):
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

        async def postback(adsid, conversion_id):
            async with session_factory() as session:
                async with session.begin():
                    return await outbox_module.enqueue_postback_report(
                        session,
                        platform="meta",
                        adsid=adsid,
                        event="Purchase",
                        conversion_id=conversion_id,
                        email=None,
                        ip=None,
                        phone=None,
                        ua=None,
                        currency="USD",
                        amount=3.0,
                        short_link_id=9,
                        cloak_name=None,
                        short_code=None,
                        click_time=None,
                    )

        direct_first_adsid = f"direct-first-{uuid.uuid4().hex}"
        direct_first_conversion = f"conversion-{uuid.uuid4().hex}"
        assert await direct(direct_first_adsid, direct_first_conversion) > 0
        with pytest.raises(outbox_module.LegacyEventIdentityConflict):
            await postback(direct_first_adsid, direct_first_conversion)

        postback_first_adsid = f"postback-first-{uuid.uuid4().hex}"
        postback_first_conversion = f"conversion-{uuid.uuid4().hex}"
        assert await postback(postback_first_adsid, postback_first_conversion) > 0
        assert await direct(postback_first_adsid, postback_first_conversion) == 0

        async with session_factory() as session:
            for adsid in (direct_first_adsid, postback_first_adsid):
                rows = list(
                    (
                        await session.execute(
                            select(ThirdPartyReportLog).where(
                                ThirdPartyReportLog.adsid == adsid
                            )
                        )
                    ).scalars().all()
                )
                assert len(rows) == 1
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_purchase_viewcontent_link_allows_only_one_concurrent_purchase(monkeypatch):
    """真实 MySQL 验证两个 Purchase 并发关联时，同一 ViewContent 只能被一个占用。"""
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

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(report_module, "AsyncSessionLocal", session_factory)

        now = get_app_now_naive().replace(microsecond=0)
        adsid = f"ci-link-{uuid.uuid4().hex}"
        pixel_id = "pixel-ci-link"
        view_key = hashlib.sha256(f"{adsid}:ViewContent".encode("utf-8")).hexdigest()
        purchase_ids = []
        purchase_tokens = [uuid.uuid4().hex, uuid.uuid4().hex]
        async with session_factory() as session:
            view_content = ThirdPartyReportLog(
                source="ci",
                adsid=adsid,
                event="ViewContent",
                event_key=view_key,
                identity_scope="platform_scoped",
                platform="meta",
                destination_pixel_id=pixel_id,
                status="success",
                created_at=now,
            )
            session.add(view_content)
            for index, token in enumerate(purchase_tokens):
                purchase = ThirdPartyReportLog(
                    source="ci",
                    adsid=adsid,
                    event="Purchase",
                    event_key=hashlib.sha256(
                        f"{adsid}:Purchase:{index}".encode("utf-8")
                    ).hexdigest(),
                    identity_scope="platform_scoped",
                    platform="meta",
                    destination_pixel_id=pixel_id,
                    status="pending",
                    report_start_time=now,
                    lease_token=token,
                )
                session.add(purchase)
                purchase_ids.append(purchase)
            await session.commit()
            view_content_id = view_content.id
            purchase_ids = [row.id for row in purchase_ids]

        async def link(index: int) -> bool:
            return await report_module._link_purchase_to_view_content(
                source="ci",
                adsid=adsid,
                conversion_id=f"ci-conversion-{index}",
                report_log_id=purchase_ids[index],
                destination_pixel_id=pixel_id,
                identity_scope="platform_scoped",
                platform="meta",
                lease_token=purchase_tokens[index],
            )

        results = await asyncio.gather(link(0), link(1))
        assert sum(results) == 1

        async with session_factory() as session:
            linked = await session.scalar(
                select(ThirdPartyReportLog).where(
                    ThirdPartyReportLog.id == view_content_id
                )
            )
            assert linked is not None
            assert linked.conversion_id in {"ci-conversion-0", "ci-conversion-1"}
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_manual_retry_is_atomic_against_admin_and_worker_races(monkeypatch):
    """真实 MySQL 验证人工重试预算原子递增，并与 Worker 认领互斥。"""
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
        admin_key = hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest()
        worker_key = hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest()

        def retryable_row(event_key: str, adsid: str) -> ThirdPartyReportLog:
            return ThirdPartyReportLog(
                source="ci",
                adsid=adsid,
                event="Purchase",
                event_key=event_key,
                identity_scope="platform_scoped",
                platform="meta",
                destination_pixel_id="pixel-ci-retry",
                status="failed",
                outbox_enqueued=True,
                attempt_count=1,
                max_attempts=5,
                manual_retry_count=0,
                report_start_time=None,
                next_retry_time=now,
                short_link_id=9901,
                cloak_name="ci-cloak",
                short_code="ci-short",
                email="retry@example.invalid",
                created_at=now,
            )

        async with session_factory() as session:
            admin_row = retryable_row(admin_key, "ci-admin-retry-race")
            worker_row = retryable_row(worker_key, "ci-worker-retry-race")
            session.add_all([admin_row, worker_row])
            await session.commit()
            admin_id, worker_id = admin_row.id, worker_row.id

        # 两个管理员同时提交同一失败事件：条件 UPDATE 必须只允许一次预算递增。
        admin_results = await asyncio.gather(
            report_module.retry_report_log(admin_id),
            report_module.retry_report_log(admin_id),
        )
        assert sorted(admin_results) == [False, True]

        async with session_factory() as session:
            admin_after = await session.get(ThirdPartyReportLog, admin_id)
            assert admin_after is not None
            assert admin_after.status == "pending"
            assert admin_after.manual_retry_count == 1
            assert admin_after.attempt_count == 0
            assert admin_after.lease_token is None

        # 管理员重新入队与 Worker 原子认领并发：最终必须只有一个有效租约，
        # 无论先后顺序如何，重试计数只能在管理员 UPDATE 成功时递增一次。
        retry_result, worker_token = await asyncio.gather(
            report_module.retry_report_log(worker_id),
            report_module._claim_report_log(
                worker_id,
                expected_scope="platform_scoped",
                platform="meta",
            ),
        )
        assert worker_token is not None
        async with session_factory() as session:
            worker_after = await session.get(ThirdPartyReportLog, worker_id)
            assert worker_after is not None
            assert worker_after.status == "pending"
            assert worker_after.lease_token == worker_token
            assert worker_after.report_start_time is not None
            assert worker_after.manual_retry_count == (1 if retry_result else 0)
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)


@pytest.mark.asyncio
async def test_mysql_manual_retry_and_pii_retention_are_mutually_exclusive(monkeypatch):
    """真实 MySQL 验证管理员重试与到期 PII 清理只能有一个先完成。"""
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
        monkeypatch.setattr(report_module, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(retention_module, "AsyncSessionLocal", session_factory)

        now = get_app_now_naive()
        old_created_at = now - timedelta(days=120)
        event_key = hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest()
        async with session_factory() as session:
            row = ThirdPartyReportLog(
                source="ci",
                adsid="ci-retry-retention-race",
                event="Purchase",
                event_key=event_key,
                identity_scope="platform_scoped",
                platform="meta",
                destination_pixel_id="pixel-ci-retention-race",
                status="failed",
                outbox_enqueued=True,
                attempt_count=5,
                max_attempts=5,
                manual_retry_count=0,
                next_retry_time=None,
                report_start_time=None,
                short_link_id=9902,
                cloak_name="ci-retention-cloak",
                short_code="ci-retention-short",
                email="retention-race@example.invalid",
                ip="203.0.113.25",
                phone="4155550199",
                ua="retention-race-agent",
                report_params='{"email":"retention-race@example.invalid"}',
                created_at=old_created_at,
            )
            session.add(row)
            await session.commit()
            report_id = row.id

        monkeypatch.setattr(retention_module, "get_app_now_naive", lambda: now)
        retry_result, retention_result = await asyncio.gather(
            report_module.retry_report_log(report_id),
            retention_module.scrub_expired_third_party_report_pii(
                retention_days=90,
                batch_size=10,
            ),
        )

        async with session_factory() as session:
            final_row = await session.get(ThirdPartyReportLog, report_id)
            assert final_row is not None
            if retry_result:
                # 重试先取得行更新资格：清理不能再把待发送载荷擦除。
                assert final_row.status == "pending"
                assert final_row.pii_scrubbed_at is None
                assert final_row.email == "retention-race@example.invalid"
                assert final_row.manual_retry_count == 1
            else:
                # 清理先取得行锁：管理员重试必须因 pii_scrubbed_at 拒绝入队。
                assert final_row.pii_scrubbed_at is not None
                assert final_row.adsid == ""
                assert final_row.email is None
                assert final_row.report_params is None
                assert final_row.status == "failed"
                assert final_row.manual_retry_count == 0
        assert retention_result["third_party_report_logs_scrubbed"] in (0, 1)
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)



@pytest.mark.asyncio
async def test_mysql_purchase_link_rejects_stale_lease_and_scrubbed_view_content(monkeypatch):
    """真实 MySQL 验证旧 Purchase Worker 与已清理 ViewContent 均不能建立关联。"""
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

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(report_module, "AsyncSessionLocal", session_factory)

        now = get_app_now_naive().replace(microsecond=0)
        pixel_id = "pixel-ci-purchase-link-guard"
        scrubbed_adsid = f"ci-scrubbed-{uuid.uuid4().hex}"
        stale_adsid = f"ci-stale-{uuid.uuid4().hex}"
        scrubbed_purchase_token = uuid.uuid4().hex
        stale_purchase_token = uuid.uuid4().hex
        scrubbed_purchase_id = None
        stale_purchase_id = None
        scrubbed_view_id = None
        stale_view_id = None

        async with session_factory() as session:
            scrubbed_purchase = ThirdPartyReportLog(
                source="ci",
                adsid=scrubbed_adsid,
                event="Purchase",
                event_key=hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest(),
                identity_scope="platform_scoped",
                platform="meta",
                destination_pixel_id=pixel_id,
                conversion_id=f"ci-conversion-scrubbed-{uuid.uuid4().hex}",
                status="pending",
                report_start_time=now,
                lease_token=scrubbed_purchase_token,
                created_at=now,
            )
            scrubbed_view = ThirdPartyReportLog(
                source="ci",
                adsid=scrubbed_adsid,
                event="ViewContent",
                event_key=hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest(),
                identity_scope="platform_scoped",
                platform="meta",
                destination_pixel_id=pixel_id,
                status="success",
                conversion_id=None,
                # 模拟已完成脱敏但关联标识因历史部分清理而仍残留的 fail-closed 边界。
                pii_scrubbed_at=now,
                created_at=now,
            )
            stale_purchase = ThirdPartyReportLog(
                source="ci",
                adsid=stale_adsid,
                event="Purchase",
                event_key=hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest(),
                identity_scope="platform_scoped",
                platform="meta",
                destination_pixel_id=pixel_id,
                conversion_id=f"ci-conversion-stale-{uuid.uuid4().hex}",
                status="pending",
                report_start_time=now - timedelta(
                    seconds=report_module.REPORT_LOG_LEASE_SECONDS + 2
                ),
                lease_token=stale_purchase_token,
                created_at=now,
            )
            stale_view = ThirdPartyReportLog(
                source="ci",
                adsid=stale_adsid,
                event="ViewContent",
                event_key=hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest(),
                identity_scope="platform_scoped",
                platform="meta",
                destination_pixel_id=pixel_id,
                status="success",
                conversion_id=None,
                pii_scrubbed_at=None,
                created_at=now,
            )
            session.add_all([scrubbed_purchase, scrubbed_view, stale_purchase, stale_view])
            await session.commit()
            scrubbed_purchase_id = scrubbed_purchase.id
            stale_purchase_id = stale_purchase.id
            scrubbed_view_id = scrubbed_view.id
            stale_view_id = stale_view.id

        scrubbed_result = await report_module._link_purchase_to_view_content(
            source="ci",
            adsid=scrubbed_adsid,
            conversion_id="must-not-restore-scrubbed-pii",
            report_log_id=scrubbed_purchase_id,
            destination_pixel_id=pixel_id,
            identity_scope="platform_scoped",
            platform="meta",
            lease_token=scrubbed_purchase_token,
        )
        stale_result = await report_module._link_purchase_to_view_content(
            source="ci",
            adsid=stale_adsid,
            conversion_id="must-not-link-from-stale-worker",
            report_log_id=stale_purchase_id,
            destination_pixel_id=pixel_id,
            identity_scope="platform_scoped",
            platform="meta",
            lease_token=stale_purchase_token,
        )

        assert scrubbed_result is False
        assert stale_result is False
        async with session_factory() as session:
            scrubbed_view = await session.get(ThirdPartyReportLog, scrubbed_view_id)
            stale_view = await session.get(ThirdPartyReportLog, stale_view_id)
            assert scrubbed_view is not None
            assert scrubbed_view.pii_scrubbed_at is not None
            assert scrubbed_view.conversion_id is None
            assert stale_view is not None
            assert stale_view.conversion_id is None
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)



@pytest.mark.asyncio
async def test_mysql_purchase_link_waits_for_pii_scrub_and_never_restores_link(monkeypatch):
    """确定性交错：清理先锁住 ViewContent，Purchase 关联等待后必须看到已清理状态。"""
    database = _create_isolated_database()
    engine = None
    cleaner_locked_view = asyncio.Event()
    release_cleaner = asyncio.Event()
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
            await connection.execute(text(
                "CREATE TABLE postback_forward_queue ("
                "id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
                "conversion_id INT NOT NULL, product_id INT NULL, publisher_id INT NULL"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            ))

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        link_waiting_for_view = asyncio.Event()

        class LinkObservingSession:
            """确认 Purchase 关联已发出 ViewContent 锁定查询后再释放清理事务。"""
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                await self.session.__aenter__()
                return self

            async def __aexit__(self, *args):
                return await self.session.__aexit__(*args)

            def __getattr__(self, name):
                return getattr(self.session, name)

            async def execute(self, statement, *args, **kwargs):
                sql = str(statement).lower()
                if (
                    "third_party_report_logs" in sql
                    and "conversion_id is null" in sql
                    and "for update" in sql
                ):
                    link_waiting_for_view.set()
                return await self.session.execute(statement, *args, **kwargs)

        monkeypatch.setattr(
            report_module,
            "AsyncSessionLocal",
            lambda: LinkObservingSession(session_factory()),
        )

        class PausingSession:
            """只在清理查询已取得 ViewContent 行锁后暂停，构造可重复的竞态时序。"""
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                await self.session.__aenter__()
                return self

            async def __aexit__(self, *args):
                return await self.session.__aexit__(*args)

            def __getattr__(self, name):
                return getattr(self.session, name)

            async def execute(self, statement, *args, **kwargs):
                result = await self.session.execute(statement, *args, **kwargs)
                lock_clause = getattr(statement, "_for_update_arg", None)
                if (
                    getattr(lock_clause, "skip_locked", False)
                    and any(
                        description.get("entity") is ThirdPartyReportLog
                        for description in getattr(statement, "column_descriptions", ())
                    )
                ):
                    # execute 返回时 SELECT ... FOR UPDATE 已完成，InnoDB 行锁已持有。
                    cleaner_locked_view.set()
                    await release_cleaner.wait()
                return result

        monkeypatch.setattr(
            retention_module,
            "AsyncSessionLocal",
            lambda: PausingSession(session_factory()),
        )
        now = get_app_now_naive()
        old_created_at = now - timedelta(days=120)
        adsid = f"ci-pii-link-race-{uuid.uuid4().hex}"
        pixel_id = "pixel-ci-pii-link-race"
        purchase_token = uuid.uuid4().hex
        view_key = hashlib.sha256(
            f"{adsid}:ViewContent:{uuid.uuid4().hex}".encode("utf-8")
        ).hexdigest()

        async with session_factory() as session:
            purchase = ThirdPartyReportLog(
                source="ci",
                adsid=adsid,
                event="Purchase",
                event_key=hashlib.sha256(uuid.uuid4().hex.encode("utf-8")).hexdigest(),
                identity_scope="platform_scoped",
                platform="meta",
                destination_pixel_id=pixel_id,
                conversion_id=f"ci-purchase-{uuid.uuid4().hex}",
                status="pending",
                report_start_time=now,
                lease_token=purchase_token,
                created_at=now,
            )
            view_content = ThirdPartyReportLog(
                source="ci",
                adsid=adsid,
                event="ViewContent",
                event_key=view_key,
                identity_scope="platform_scoped",
                platform="meta",
                destination_pixel_id=pixel_id,
                conversion_id=None,
                status="success",
                outbox_enqueued=False,
                report_start_time=None,
                email="pii-race@example.invalid",
                ip="203.0.113.77",
                phone="4155550177",
                ua="pii-race-agent",
                report_params='{"email":"pii-race@example.invalid"}',
                created_at=old_created_at,
            )
            session.add_all([purchase, view_content])
            await session.commit()
            purchase_id = purchase.id
            view_content_id = view_content.id

        monkeypatch.setattr(retention_module, "get_app_now_naive", lambda: now)
        cleaner_task = asyncio.create_task(
            retention_module.scrub_expired_third_party_report_pii(
                retention_days=90,
                batch_size=10,
            )
        )
        await asyncio.wait_for(cleaner_locked_view.wait(), timeout=10)

        link_task = asyncio.create_task(
            report_module._link_purchase_to_view_content(
                source="ci",
                adsid=adsid,
                conversion_id="must-not-be-restored-after-scrub",
                report_log_id=purchase_id,
                destination_pixel_id=pixel_id,
                identity_scope="platform_scoped",
                platform="meta",
                lease_token=purchase_token,
            )
        )
        # 等待关联事务确实发出 ViewContent SELECT FOR UPDATE（此时会被清理锁阻塞）。
        await asyncio.wait_for(link_waiting_for_view.wait(), timeout=10)
        release_cleaner.set()
        cleaner_result, link_result = await asyncio.gather(cleaner_task, link_task)

        assert cleaner_result["third_party_report_logs_scrubbed"] == 1
        assert link_result is False
        async with session_factory() as session:
            final_view = await session.get(ThirdPartyReportLog, view_content_id)
            assert final_view is not None
            assert final_view.pii_scrubbed_at is not None
            assert final_view.adsid == ""
            assert final_view.email is None
            assert final_view.report_params is None
            assert final_view.conversion_id is None
    finally:
        release_cleaner.set()
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)
