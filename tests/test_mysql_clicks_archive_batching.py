"""点击归档真实 MySQL 集成测试：仅允许连接 CI 本机隔离 platform_ci 数据库。"""
from __future__ import annotations

import asyncio
import ipaddress
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.tracking import clicks_archive_service as archive_module


HOST = os.getenv("MYSQL_INTEGRATION_HOST")
DATABASE = os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci")
_DESTRUCTIVE_TESTS_ENABLED = os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"


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
    and _DESTRUCTIVE_TESTS_ENABLED
    and _is_loopback_host(HOST)
    and DATABASE == "platform_ci"
)

if (
    os.getenv("GITHUB_ACTIONS") == "true"
    or (os.getenv("UNIT_TEST") == "1" and HOST)
) and not _SAFE_MYSQL_CI:
    raise RuntimeError(
        "拒绝执行破坏性点击归档 MySQL 测试：必须使用 loopback 主机、platform_ci 数据库，"
        "并显式设置 MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS=1"
    )

pytestmark = pytest.mark.skipif(
    not _SAFE_MYSQL_CI,
    reason="仅在 GitHub Actions 本机隔离 MySQL 服务中运行点击归档集成测试",
)


_CLICKS_DDL = """
CREATE TABLE clicks (
    id INT NOT NULL AUTO_INCREMENT,
    click_id VARCHAR(255) NOT NULL,
    offer_id INT NULL,
    publisher_id INT NULL,
    advertiser_id INT NULL,
    short_link_id INT NULL,
    click_time DATETIME NOT NULL,
    ip VARCHAR(50) NULL,
    device VARCHAR(100) NULL,
    country VARCHAR(50) NULL,
    user_agent TEXT NULL,
    referer TEXT NULL,
    conversion_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    os VARCHAR(50) NULL,
    os_version VARCHAR(50) NULL,
    browser VARCHAR(50) NULL,
    browser_version VARCHAR(50) NULL,
    accept_language VARCHAR(200) NULL,
    accept_encoding VARCHAR(200) NULL,
    is_bot TINYINT(1) NOT NULL DEFAULT 0,
    device_type VARCHAR(20) NULL,
    device_brand VARCHAR(50) NULL,
    device_model VARCHAR(100) NULL,
    url_params TEXT NULL,
    all_headers TEXT NULL,
    original_request_url TEXT NULL,
    final_redirect_url TEXT NULL,
    PRIMARY KEY (id),
    KEY idx_click_time (click_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _engine():
    url = URL.create(
        "mysql+aiomysql",
        username=os.getenv("MYSQL_INTEGRATION_USER", "root"),
        password=os.getenv("MYSQL_INTEGRATION_PASSWORD", ""),
        host=HOST,
        port=int(os.getenv("MYSQL_INTEGRATION_PORT", "3306")),
        database=DATABASE,
        query={"charset": "utf8mb4"},
    )
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=4,
        max_overflow=0,
    )


async def _reset_tables(engine, rows):
    async with engine.begin() as connection:
        await connection.exec_driver_sql("DROP TABLE IF EXISTS clicks_archive")
        await connection.exec_driver_sql("DROP TABLE IF EXISTS clicks")
        await connection.exec_driver_sql(_CLICKS_DDL)
        await connection.exec_driver_sql(archive_module._CREATE_ARCHIVE_TABLE_SQL)
        if rows:
            await connection.execute(
                text(
                    """
                    INSERT INTO clicks
                    (click_id, click_time, original_request_url, final_redirect_url)
                    VALUES (:click_id, :click_time, :original_request_url, :final_redirect_url)
                    """
                ),
                rows,
            )


async def _drop_tables(engine):
    async with engine.begin() as connection:
        await connection.exec_driver_sql("DROP TABLE IF EXISTS clicks_archive")
        await connection.exec_driver_sql("DROP TABLE IF EXISTS clicks")


async def _run_archive(session_factory, service, *, batch_size):
    async with session_factory() as session:
        return await service.archive_old_clicks(
            session,
            days=90,
            batch_size=batch_size,
        )


@pytest.mark.asyncio
async def test_mysql_archive_batches_preserve_url_fields_and_leave_recent_clicks(monkeypatch):
    engine = _engine()
    try:
        now = datetime(2026, 11, 22, 12, 0, 0)
        old_time = now - timedelta(days=120)
        recent_time = now - timedelta(days=10)
        await _reset_tables(
            engine,
            [
                {
                    "click_id": f"old-{index}",
                    "click_time": old_time,
                    "original_request_url": f"https://example.test/click/{index}?fbclid=test-{index}",
                    "final_redirect_url": f"https://landing.test/{index}",
                }
                for index in range(3)
            ]
            + [
                {
                    "click_id": "recent-1",
                    "click_time": recent_time,
                    "original_request_url": "https://example.test/recent",
                    "final_redirect_url": "https://landing.test/recent",
                }
            ],
        )

        service = archive_module.ClicksArchiveService()

        async def _do_not_skip(_db):
            return False

        async def _table_already_exists(_db):
            return None

        monkeypatch.setattr(service, "should_skip_archive", _do_not_skip)
        monkeypatch.setattr(service, "_ensure_archive_table", _table_already_exists)
        monkeypatch.setattr(archive_module, "get_app_now_naive", lambda: now)
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        result = await _run_archive(session_factory, service, batch_size=2)

        async with engine.connect() as connection:
            archived = (
                await connection.execute(
                    text(
                        "SELECT click_id, original_request_url, final_redirect_url "
                        "FROM clicks_archive ORDER BY id"
                    )
                )
            ).all()
            remaining = (
                await connection.execute(text("SELECT click_id FROM clicks ORDER BY id"))
            ).scalars().all()

        assert result["archived_count"] == 3
        assert result["deleted_count"] == 3
        assert result["batch_count"] == 2
        assert [row[0] for row in archived] == ["old-0", "old-1", "old-2"]
        assert archived[0][1] == "https://example.test/click/0?fbclid=test-0"
        assert archived[0][2] == "https://landing.test/0"
        assert remaining == ["recent-1"]
    finally:
        await _drop_tables(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_concurrent_archive_workers_do_not_duplicate_or_lose_clicks(monkeypatch):
    engine = _engine()
    try:
        now = datetime(2026, 11, 22, 12, 0, 0)
        old_time = now - timedelta(days=120)
        row_count = 40
        await _reset_tables(
            engine,
            [
                {
                    "click_id": f"concurrent-{index}",
                    "click_time": old_time,
                    "original_request_url": f"https://example.test/concurrent/{index}",
                    "final_redirect_url": f"https://landing.test/concurrent/{index}",
                }
                for index in range(row_count)
            ],
        )

        service = archive_module.ClicksArchiveService()

        async def _do_not_skip(_db):
            return False

        async def _table_already_exists(_db):
            return None

        monkeypatch.setattr(service, "should_skip_archive", _do_not_skip)
        monkeypatch.setattr(service, "_ensure_archive_table", _table_already_exists)
        monkeypatch.setattr(archive_module, "get_app_now_naive", lambda: now)
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        first, second = await asyncio.gather(
            _run_archive(session_factory, service, batch_size=5),
            _run_archive(session_factory, service, batch_size=5),
        )

        async with engine.connect() as connection:
            archive_count = await connection.scalar(
                text("SELECT COUNT(*) FROM clicks_archive")
            )
            distinct_archive_ids = await connection.scalar(
                text("SELECT COUNT(DISTINCT id) FROM clicks_archive")
            )
            source_count = await connection.scalar(text("SELECT COUNT(*) FROM clicks"))

        assert first["archived_count"] + second["archived_count"] == row_count
        assert archive_count == row_count
        assert distinct_archive_ids == row_count
        assert source_count == 0
    finally:
        await _drop_tables(engine)
        await engine.dispose()
