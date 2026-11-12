"""第三方 Report Outbox 的真实 MySQL 并发认领集成测试。

仅连接 CI 显式提供的本机临时 MySQL platform_ci；禁止访问远程/生产数据库。
"""
import asyncio
import hashlib
import ipaddress
import os
import uuid
from datetime import timedelta
from urllib.parse import quote_plus

import pymysql
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import third_party_report as report_module
from app.core.utils import get_app_now_naive
from app.models.third_party import ThirdPartyReportLog


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
