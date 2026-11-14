"""真实隔离 MySQL 运行账号权限边界测试。

只允许 GitHub Actions 中的 loopback 临时 MySQL。测试使用独立 schema 和临时账号，
由测试管理员预置表结构，再验证应用运行账号仅凭 DML 权限即可执行管理员 bootstrap。
当前 lifespan 已先执行只读 migration revision/ORM drift gate，再调用仅包含管理员账户 DML bootstrap 的 init_db；schema DDL 必须由独立 Migration Runner 和预置 provisioning 完成。本测试验证预置 users 表上的 DML 可用且运行账号没有 CREATE 权限，不等于覆盖所有业务表/所有 SQL 操作的最小权限清单。
"""
from __future__ import annotations

import asyncio
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


class _TwoPartyBarrier:
    """让两个真实 DB session 都完成首次 SELECT 后再继续，稳定复现启动竞争。"""

    def __init__(self):
        self._arrived = 0
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()

    async def wait(self):
        async with self._lock:
            self._arrived += 1
            if self._arrived == 2:
                self._ready.set()
        await asyncio.wait_for(self._ready.wait(), timeout=10)


@pytest.mark.asyncio
async def test_mysql_runtime_account_can_bootstrap_admin_but_cannot_run_ddl(monkeypatch):
    """真实 MySQL 验证低权限 DML、双 Worker 首次启动竞争和 DDL 拒绝边界。"""
    username = "platform_ci_runtime"
    password = secrets.token_hex(24)
    root_engine = None
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

        # 表结构由隔离测试管理员预置；运行账号从未获得 CREATE/ALTER/DROP 权限。
        root_url = URL.create(
            "mysql+pymysql",
            username=ROOT_USER,
            password=ROOT_PASSWORD,
            host=HOST,
            port=PORT,
            database=DATABASE,
            query={"charset": "utf8mb4"},
        )
        root_engine = create_engine(root_url, pool_pre_ping=True)
        User.__table__.create(root_engine)
        with root_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE runtime_ddl_probe (id INT NOT NULL PRIMARY KEY)"
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
        async_url = runtime_url.set(drivername="mysql+aiomysql")
        async_engine = create_async_engine(async_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

        monkeypatch.setattr(database_module, "AsyncSessionLocal", session_factory)
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

        # 强制两个 Worker 都先读到“尚无管理员”，再并发竞争唯一键。
        barrier = _TwoPartyBarrier()

        class _BarrierSession:
            def __init__(self, session):
                self._session = session
                self._first_execute = True

            async def __aenter__(self):
                await self._session.__aenter__()
                return self

            async def __aexit__(self, *args):
                return await self._session.__aexit__(*args)

            async def execute(self, *args, **kwargs):
                result = await self._session.execute(*args, **kwargs)
                if self._first_execute:
                    self._first_execute = False
                    await barrier.wait()
                return result

            def __getattr__(self, name):
                return getattr(self._session, name)

        monkeypatch.setattr(
            database_module,
            "AsyncSessionLocal",
            lambda: _BarrierSession(session_factory()),
        )
        await asyncio.gather(database_module.init_db(), database_module.init_db())

        # 恢复普通 session factory，验证已存在管理员时重复启动保持幂等。
        monkeypatch.setattr(database_module, "AsyncSessionLocal", session_factory)
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
                cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
                assert cursor.fetchone()[0] == 1

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
                ddl_statements = (
                    "CREATE TABLE runtime_ddl_must_be_denied (id INT NOT NULL)",
                    "ALTER TABLE runtime_ddl_probe ADD COLUMN forbidden_column INT NULL",
                    "CREATE INDEX runtime_ddl_must_be_denied_idx ON runtime_ddl_probe (id)",
                    "DROP TABLE runtime_ddl_probe",
                )
                for statement in ddl_statements:
                    with pytest.raises(pymysql.err.OperationalError) as denied:
                        cursor.execute(statement)
                    assert denied.value.args[0] == 1142, statement
        finally:
            runtime.close()
    finally:
        if async_engine is not None:
            await async_engine.dispose()
        if root_engine is not None:
            root_engine.dispose()
        with root.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{DATABASE}`")
            cursor.execute(f"DROP USER IF EXISTS '{username}'@'%'")
        root.close()
