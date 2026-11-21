"""待确认记录锁查询必须支持读取已处理状态用于审计分类。"""
from sqlalchemy.dialects import mysql

from app.core.postback.pending_lock import build_pending_for_update_statement
from app.models.models import PendingPostbackConversion


def test_pending_lock_can_read_any_status_without_dropping_row_lock():
    statement = build_pending_for_update_statement(
        PendingPostbackConversion,
        123,
        status=None,
    )
    sql = str(statement.compile(dialect=mysql.dialect()))

    assert "pending_postback_conversions.id = 123" in sql
    assert "pending_postback_conversions.status" not in sql
    assert sql.rstrip().endswith("FOR UPDATE")


def test_pending_lock_defaults_to_pending_status():
    statement = build_pending_for_update_statement(
        PendingPostbackConversion,
        123,
    )
    sql = str(statement.compile(dialect=mysql.dialect()))

    assert "pending_postback_conversions.status = 'pending'" in sql
    assert sql.rstrip().endswith("FOR UPDATE")


# 以下测试只允许连接 GitHub Actions 创建的 loopback MySQL platform_ci，
# 并为每次运行创建独立数据库；本地未显式授权时自动跳过。
import asyncio
import os
import uuid
from urllib.parse import quote_plus

import pymysql
import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


_MYSQL_HOST = os.getenv("MYSQL_INTEGRATION_HOST")
_MYSQL_DATABASE = os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci")
_MYSQL_ENABLED = (
    os.getenv("UNIT_TEST") == "1"
    and os.getenv("GITHUB_ACTIONS") == "true"
    and os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _MYSQL_HOST in {"127.0.0.1", "localhost", "::1"}
    and _MYSQL_DATABASE == "platform_ci"
)
if os.getenv("GITHUB_ACTIONS") == "true" and not _MYSQL_ENABLED:
    raise RuntimeError("拒绝运行 Postback 行锁集成测试：MySQL 目标未通过隔离校验")


@pytest.mark.skipif(not _MYSQL_ENABLED, reason="仅在隔离的 GitHub Actions MySQL 8.0 服务中运行")
@pytest.mark.asyncio
async def test_mysql_innodb_pending_lock_serializes_concurrent_approval_reads():
    database = f"ci_pending_lock_{uuid.uuid4().hex[:12]}"
    host = _MYSQL_HOST
    port = int(os.getenv("MYSQL_INTEGRATION_PORT", "3306"))
    user = os.getenv("MYSQL_INTEGRATION_USER", "root")
    password = os.getenv("MYSQL_INTEGRATION_PASSWORD", "")
    admin = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=_MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        admin.close()

    password_url = quote_plus(password)
    user_url = quote_plus(user)
    engine = create_async_engine(
        f"mysql+aiomysql://{user_url}:{password_url}@{host}:{port}/{database}?charset=utf8mb4",
        pool_pre_ping=True,
    )
    metadata = MetaData()
    pending_table = Table(
        "pending_postback_conversions",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("status", String(20), nullable=False),
        mysql_engine="InnoDB",
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            inserted = await connection.execute(
                pending_table.insert().values(status="pending")
            )
            pending_id = inserted.inserted_primary_key[0]

        first_locked = asyncio.Event()
        release_first = asyncio.Event()
        second_started = asyncio.Event()
        second_status = []

        async def first_approval():
            async with factory() as session:
                result = await session.execute(
                    build_pending_for_update_statement(
                        pending_table, pending_id, status=None
                    )
                )
                assert result.mappings().one()["status"] == "pending"
                first_locked.set()
                await release_first.wait()
                await session.execute(
                    update(pending_table)
                    .where(pending_table.c.id == pending_id)
                    .values(status="approved")
                )
                await session.commit()

        async def second_approval():
            await first_locked.wait()
            async with factory() as session:
                second_started.set()
                result = await session.execute(
                    build_pending_for_update_statement(
                        pending_table, pending_id, status=None
                    )
                )
                row = result.mappings().one()
                second_status.append(row["status"])
                await session.rollback()

        first_task = asyncio.create_task(first_approval())
        second_task = asyncio.create_task(second_approval())
        await asyncio.wait_for(second_started.wait(), timeout=5)
        await asyncio.sleep(0.15)
        # 第二个事务必须等待第一个事务释放 InnoDB 行锁。
        second_was_blocked = not second_task.done()
        release_first.set()
        await asyncio.wait_for(
            asyncio.gather(first_task, second_task),
            timeout=15,
        )
        assert second_was_blocked
        assert second_status == ["approved"]
    finally:
        await engine.dispose()
        cleanup = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=_MYSQL_DATABASE,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=5,
        )
        try:
            with cleanup.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        finally:
            cleanup.close()
