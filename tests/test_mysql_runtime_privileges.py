"""真实隔离 MySQL 运行账号权限边界测试。

只允许 GitHub Actions 中的 loopback 临时 MySQL。测试使用独立 schema 和临时账号，
验证管理员 bootstrap 所需 DML 权限，并确认运行账号不能执行 DDL。
这不代表当前 lifespan 已能使用低权限账号启动：create_database/create_all 仍需单独拆分。
"""
from __future__ import annotations

import ipaddress
import os
import secrets

import pytest
import pymysql
from sqlalchemy import URL, create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import database as database_module
from app.models.models import User


HOST = os.getenv("MYSQL_INTEGRATION_HOST")
PORT = int(os.getenv("MYSQL_INTEGRATION_PORT", "3306"))
ROOT_USER = os.getenv("MYSQL_INTEGRATION_USER", "root")
ROOT_PASSWORD = os.getenv("MYSQL_INTEGRATION_PASSWORD", "")
DATABASE = "platform_ci_runtime_privileges"


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
    and os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _is_loopback_host(HOST)
    and os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci") == "platform_ci"
)
if (
    os.getenv("GITHUB_ACTIONS") == "true"
    or (os.getenv("UNIT_TEST") == "1" and HOST)
) and not _SAFE_MYSQL_CI:
    raise RuntimeError("拒绝运行 MySQL 运行账号权限测试：必须使用 GitHub Actions loopback 临时 MySQL")

pytestmark = pytest.mark.skipif(
    not _SAFE_MYSQL_CI,
    reason="仅在 GitHub Actions loopback 临时 MySQL 中运行",
)


def _root_connect(database: str | None = None):
    return pymysql.connect(
        host=HOST,
        port=PORT,
        user=ROOT_USER,
        password=ROOT_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )


@pytest.mark.asyncio
async def test_mysql_runtime_account_can_bootstrap_admin_but_cannot_run_ddl(monkeypatch):
    """真实 MySQL 验证 init_db 的 DML 能力与运行账号的 DDL 拒绝边界。"""
    username = "platform_ci_runtime"
    password = secrets.token_hex(24)
    sync_engine = None
    async_engine = None
    root = _root_connect()

    try:
        with root.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{DATABASE}`")
            cursor.execute(f"DROP USER IF EXISTS '{username}'@'%'")
            cursor.execute(
                f"CREATE DATABASE `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(f"CREATE USER '{username}'@'%' IDENTIFIED BY '{password}'")
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{DATABASE}`.* TO '{username}'@'%'"
            )

        runtime_url = URL.create(
            "mysql+pymysql",
            username=username,
            password=password,
            host=HOST,
            port=PORT,
            database=DATABASE,
            query={"charset": "utf8mb4"},
        )
        sync_engine = create_engine(runtime_url, pool_pre_ping=True)
        User.__table__.create(sync_engine)

        async_url = runtime_url.set(drivername="mysql+aiomysql")
        async_engine = create_async_engine(async_url, pool_pre_ping=True)
        monkeypatch.setattr(
            database_module,
            "AsyncSessionLocal",
            async_sessionmaker(async_engine, expire_on_commit=False),
        )
        monkeypatch.setattr(database_module.settings, "FIRST_SUPERUSER", "runtime-ci-admin")
        monkeypatch.setattr(
            database_module.settings,
            "FIRST_SUPERUSER_PASSWORD",
            "runtime-ci-only-password",
        )
        monkeypatch.setattr(
            database_module.User,
            "set_password",
            lambda self, value: setattr(self, "hashed_password", "ci-test-hash"),
        )

        await database_module.init_db()
        await database_module.init_db()

        with _root_connect(DATABASE) as verify:
            with verify.cursor() as cursor:
                cursor.execute(
                    "SELECT username, role FROM users WHERE username = %s",
                    ("runtime-ci-admin",),
                )
                row = cursor.fetchone()
                assert row is not None
                assert row[0] == "runtime-ci-admin"

        runtime = pymysql.connect(
            host=HOST,
            port=PORT,
            user=username,
            password=password,
            database=DATABASE,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=5,
        )
        try:
            with runtime.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM users")
                assert cursor.fetchone()[0] == 1
                with pytest.raises(pymysql.err.OperationalError) as denied:
                    cursor.execute(
                        "CREATE TABLE runtime_ddl_must_be_denied (id INT NOT NULL)"
                    )
                assert denied.value.args[0] == 1142
        finally:
            runtime.close()
    finally:
        if async_engine is not None:
            await async_engine.dispose()
        if sync_engine is not None:
            sync_engine.dispose()
        with root.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{DATABASE}`")
            cursor.execute(f"DROP USER IF EXISTS '{username}'@'%'")
        root.close()
