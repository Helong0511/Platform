"""定时任务同步的 MySQL 多 Worker 并发集成测试。

仅允许 GitHub Actions 提供的 loopback 临时 MySQL platform_ci；禁止访问远程或生产数据库。
"""

import asyncio
import os
import uuid
from urllib.parse import quote_plus

import pymysql
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.system import ScheduledTask
from app.scheduler_module import task_init


MYSQL_HOST = os.getenv("MYSQL_INTEGRATION_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_INTEGRATION_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_INTEGRATION_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_INTEGRATION_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci")


def _is_loopback_host(host: str | None) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


_SAFE_MYSQL_TARGET = (
    os.getenv("GITHUB_ACTIONS") == "true"
    and os.getenv("UNIT_TEST") == "1"
    and os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _is_loopback_host(MYSQL_HOST)
    and MYSQL_DATABASE == "platform_ci"
)

if os.getenv("GITHUB_ACTIONS") == "true" and not _SAFE_MYSQL_TARGET:
    raise RuntimeError(
        "拒绝执行定时任务同步 MySQL 集成测试：必须使用 loopback platform_ci "
        "并显式启用 MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS=1"
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
    )


def _create_isolated_database() -> str:
    database = f"platform_ci_task_sync_{uuid.uuid4().hex[:12]}"
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
    connection = _admin_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_mysql_two_workers_sync_same_task_config_without_duplicates(monkeypatch):
    """两个 Worker 同时首次同步同一批任务，最终应完整且无重复记录。"""
    database = _create_isolated_database()
    engine = None
    try:
        user = quote_plus(MYSQL_USER)
        password = quote_plus(MYSQL_PASSWORD)
        engine = create_async_engine(
            f"mysql+aiomysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}"
            "?charset=utf8mb4",
            pool_size=4,
            max_overflow=0,
            pool_pre_ping=True,
        )
        async with engine.begin() as connection:
            await connection.run_sync(ScheduledTask.__table__.create)

        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(task_init, "AsyncSessionLocal", factory)
        monkeypatch.setattr(
            task_init,
            "TASK_CONFIGS",
            {
                f"task-{index}": {
                    "task_name": f"并发同步任务-{index}",
                    "task_module": "app.scheduler_module.tasks.test_tasks",
                    "task_function": f"run_{index}",
                    "cron_expression": "*/5 * * * *",
                    "description": f"并发同步测试任务 {index}",
                }
                for index in range(8)
            },
        )

        await asyncio.gather(
            task_init.init_scheduled_tasks_in_db(),
            task_init.init_scheduled_tasks_in_db(),
        )

        async with factory() as session:
            rows = list((await session.scalars(select(ScheduledTask))).all())
            names = [row.task_name for row in rows]
            assert len(rows) == 8
            assert len(names) == len(set(names))
            assert set(names) == {
                f"并发同步任务-{index}" for index in range(8)
            }
    finally:
        if engine is not None:
            await engine.dispose()
        _drop_isolated_database(database)
