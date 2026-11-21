"""独立 Migration Runner 的真实 MySQL 隔离集成测试。

只允许 GitHub Actions loopback 临时 MySQL；数据库名随机生成并在 finally 中删除。
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import secrets
from pathlib import Path

import pytest
import pymysql
from sqlalchemy import URL

from app.db.migrations.ledger import MigrationLedgerError
from app.db.migrations.manifest import Migration
from app.db.migrations.runner import (
    MigrationExecutionError,
    MigrationLockUnavailable,
    MigrationRunnerError,
    _migration_lock_name,
    apply_migrations,
    read_migration_status,
)


HOST = os.getenv("MYSQL_INTEGRATION_HOST")
PORT = int(os.getenv("MYSQL_INTEGRATION_PORT", "3306"))
ROOT_USER = os.getenv("MYSQL_INTEGRATION_USER", "root")
ROOT_PASSWORD = os.getenv("MYSQL_INTEGRATION_PASSWORD", "")


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
    raise RuntimeError(
        "拒绝运行 Migration Runner 集成测试：必须使用 GitHub Actions loopback 临时 MySQL"
    )

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


def _create_database() -> str:
    database = f"platform_ci_mr_{secrets.token_hex(5)}"
    connection = _root_connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
            # CI 专用运行账号只获当前随机测试库权限，验证真实服务端身份。
            cursor.execute(
                f"GRANT SELECT ON `{database}`.* "
                "TO 'platform_application_runtime'@'%'"
            )
    finally:
        connection.close()
    return database


def _drop_database(database: str) -> None:
    connection = _root_connect()
    try:
        with connection.cursor() as cursor:
            # 删除随机测试库前撤销该库的临时授权，避免 CI 累积残留授权记录。
            cursor.execute(
                f"REVOKE ALL PRIVILEGES ON `{database}`.* "
                "FROM 'platform_application_runtime'@'%'"
            )
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()


def _database_url(database: str) -> str:
    return URL.create(
        "mysql+aiomysql",
        username=ROOT_USER,
        password=ROOT_PASSWORD,
        host=HOST,
        port=PORT,
        database=database,
        query={"charset": "utf8mb4"},
    ).render_as_string(hide_password=False)


def _application_database_url(database: str) -> str:
    return URL.create(
        "mysql+aiomysql",
        username="platform_application_runtime",
        password="runtime-only",
        host=HOST,
        port=PORT,
        database=database,
        query={"charset": "utf8mb4"},
    ).render_as_string(hide_password=False)


def _write_migrations(tmp_path: Path, definitions):
    migrations = []
    for definition in definitions:
        revision, sql = definition[:2]
        backfill_handler = definition[2] if len(definition) > 2 else None
        relative = f"sql/migrations/{revision}.sql"
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sql, encoding="utf-8")
        migrations.append(
            Migration(
                revision=revision,
                path=relative,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                backfill_handler=backfill_handler,
            )
        )
    return tuple(migrations)


@pytest.mark.asyncio
async def test_runner_applies_in_order_and_is_idempotent(tmp_path: Path):
    database = _create_database()
    try:
        migrations = _write_migrations(
            tmp_path,
            [
                (
                    "20261110_runner_create",
                    "CREATE TABLE runner_probe ("
                    "id INT NOT NULL PRIMARY KEY, value VARCHAR(32) NOT NULL"
                    ") ENGINE=InnoDB;",
                ),
                (
                    "20261111_runner_alter",
                    "ALTER TABLE runner_probe "
                    "ADD COLUMN enabled TINYINT NOT NULL DEFAULT 1;",
                ),
            ],
        )
        url = _database_url(database)

        applied = await apply_migrations(
            url, application_database_url=_application_database_url(database), repository_root=tmp_path, migrations=migrations
        )
        assert applied == tuple(item.revision for item in migrations)

        # 应用身份在迁移目标库只获得只读连接所需的 SELECT；不得继承迁移 DDL 权限。
        runtime = pymysql.connect(
            host=HOST,
            port=PORT,
            user="platform_application_runtime",
            password="runtime-only",
            database=database,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=5,
        )
        try:
            with runtime.cursor() as cursor:
                cursor.execute("SELECT CURRENT_USER(), DATABASE()")
                identity, selected_database = cursor.fetchone()
                assert identity.casefold().startswith("platform_application_runtime@")
                assert selected_database == database
                cursor.execute("SELECT COUNT(*) FROM runner_probe")
                assert cursor.fetchone()[0] == 0
                denied_statements = (
                    "CREATE TABLE runtime_must_not_ddl (id INT NOT NULL)",
                    "ALTER TABLE runner_probe ADD COLUMN forbidden INT NULL",
                    "CREATE INDEX runtime_forbidden_idx ON runner_probe (id)",
                    "DROP TABLE runner_probe",
                )
                for statement in denied_statements:
                    with pytest.raises(pymysql.err.OperationalError) as denied:
                        cursor.execute(statement)
                    assert denied.value.args[0] == 1142, statement
        finally:
            runtime.close()

        # 第二次执行必须只读 ledger 并返回空计划，不重复执行 DDL。
        assert await apply_migrations(
            url, application_database_url=_application_database_url(database), repository_root=tmp_path, migrations=migrations
        ) == ()

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SHOW COLUMNS FROM runner_probe")
                columns = {row[0] for row in cursor.fetchall()}
                assert columns == {"id", "value", "enabled"}
                cursor.execute(
                    "SELECT revision, status, execution_order "
                    "FROM platform_schema_migrations ORDER BY execution_order"
                )
                rows = cursor.fetchall()
                assert rows == (
                    (migrations[0].revision, "applied", 1),
                    (migrations[1].revision, "applied", 2),
                )
    finally:
        _drop_database(database)


@pytest.mark.asyncio
async def test_runner_requires_exclusive_same_database_get_lock(tmp_path: Path):
    database = _create_database()
    lock_connection = _root_connect(database)
    try:
        migrations = _write_migrations(
            tmp_path,
            [("20261110_runner_lock", "CREATE TABLE lock_probe (id INT PRIMARY KEY);")],
        )
        lock_name = _migration_lock_name(database)
        with lock_connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0)", (lock_name,))
            assert cursor.fetchone()[0] == 1

        with pytest.raises(MigrationLockUnavailable):
            await apply_migrations(
                _database_url(database),
                application_database_url=_application_database_url(database),
                repository_root=tmp_path,
                migrations=migrations,
                lock_timeout=0,
            )

        with lock_connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'platform_schema_migrations'",
                (database,),
            )
            assert cursor.fetchone()[0] == 0
    finally:
        try:
            with lock_connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (_migration_lock_name(database),))
        finally:
            lock_connection.close()
            _drop_database(database)


@pytest.mark.asyncio
async def test_runner_records_partial_ddl_failure_and_refuses_automatic_retry(tmp_path: Path):
    database = _create_database()
    try:
        migrations = _write_migrations(
            tmp_path,
            [
                (
                    "20261110_runner_partial",
                    "CREATE TABLE partial_probe (id INT NOT NULL PRIMARY KEY) ENGINE=InnoDB; "
                    "ALTER TABLE missing_runner_table ADD COLUMN unsafe_retry INT;",
                )
            ],
        )
        url = _database_url(database)
        with pytest.raises(MigrationExecutionError):
            await apply_migrations(
                url, application_database_url=_application_database_url(database), repository_root=tmp_path, migrations=migrations
            )

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status, error_type FROM platform_schema_migrations "
                    "WHERE revision = %s",
                    (migrations[0].revision,),
                )
                row = cursor.fetchone()
                assert row[0] == "failed"
                assert row[1]
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'partial_probe'",
                    (database,),
                )
                assert cursor.fetchone()[0] == 1

        # MySQL DDL 已部分提交；Runner 不得猜测性重跑。
        with pytest.raises(MigrationLedgerError, match="manual DDL recovery is required"):
            await apply_migrations(
                url, application_database_url=_application_database_url(database), repository_root=tmp_path, migrations=migrations
            )
    finally:
        _drop_database(database)


@pytest.mark.asyncio
async def test_runner_rejects_wrong_same_name_ledger_table(tmp_path: Path):
    database = _create_database()
    try:
        migrations = _write_migrations(
            tmp_path,
            [("20261110_runner_guard", "CREATE TABLE must_not_run (id INT PRIMARY KEY);")],
        )
        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE platform_schema_migrations ("
                    "revision VARCHAR(64) NOT NULL PRIMARY KEY"
                    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )

        with pytest.raises(MigrationRunnerError, match="ledger"):
            await apply_migrations(
                _database_url(database),
                application_database_url=_application_database_url(database),
                repository_root=tmp_path,
                migrations=migrations,
            )

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'must_not_run'",
                    (database,),
                )
                assert cursor.fetchone()[0] == 0
    finally:
        _drop_database(database)


def test_runner_rejects_reusing_application_database_account():
    url = "mysql+aiomysql://same_user:secret@127.0.0.1:3306/platform"
    with pytest.raises(MigrationRunnerError, match="独立于应用运行账号"):
        from app.db.migrations.runner import _ensure_distinct_database_account
        from sqlalchemy.engine import make_url

        _ensure_distinct_database_account(make_url(url), url)


def test_runner_rejects_migration_target_database_different_from_application():
    from app.db.migrations.runner import (
        MigrationRunnerError,
        _ensure_distinct_database_account,
    )
    from sqlalchemy.engine import make_url

    migration_url = make_url(
        "mysql+aiomysql://migration_user:secret@127.0.0.1:3306/platform_migrations"
    )
    application_url = (
        "mysql+aiomysql://application_user:secret@127.0.0.1:3306/platform"
    )

    with pytest.raises(MigrationRunnerError, match="同一个数据库名"):
        _ensure_distinct_database_account(migration_url, application_url)


def test_runner_rejects_application_mysql_url_without_database_name():
    from app.db.migrations.runner import (
        MigrationRunnerError,
        _ensure_distinct_database_account,
    )
    from sqlalchemy.engine import make_url

    migration_url = make_url(
        "mysql+aiomysql://migration_user:secret@127.0.0.1:3306/platform"
    )
    application_url = "mysql+aiomysql://application_user:secret@127.0.0.1:3306/"

    with pytest.raises(MigrationRunnerError, match="应用数据库 DSN"):
        _ensure_distinct_database_account(migration_url, application_url)


@pytest.mark.asyncio
async def test_status_is_read_only_for_empty_database_and_reports_ledger_rows(tmp_path: Path):
    database = _create_database()
    try:
        url = _database_url(database)
        app_url = _application_database_url(database)
        assert await read_migration_status(
            url, application_database_url=app_url
        ) == ()

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'platform_schema_migrations'",
                    (database,),
                )
                assert cursor.fetchone()[0] == 0

        migrations = _write_migrations(
            tmp_path,
            [("20261110_runner_status", "CREATE TABLE status_probe (id INT PRIMARY KEY);")],
        )
        await apply_migrations(
            url,
            application_database_url=app_url,
            repository_root=tmp_path,
            migrations=migrations,
        )
        rows = await read_migration_status(url, application_database_url=app_url)
        assert len(rows) == 1
        assert rows[0]["revision"] == migrations[0].revision
        assert rows[0]["status"] == "applied"
        assert rows[0]["execution_order"] == 1
    finally:
        _drop_database(database)

def test_runner_rejects_migration_target_on_different_mysql_host():
    from app.db.migrations.runner import (
        MigrationRunnerError,
        _ensure_distinct_database_account,
    )
    from sqlalchemy.engine import make_url

    migration_url = make_url(
        "mysql+aiomysql://migration_user:secret@migration-db.internal:3306/platform"
    )
    application_url = (
        "mysql+aiomysql://application_user:secret@app-db.internal:3306/platform"
    )

    with pytest.raises(MigrationRunnerError, match="同一个 MySQL 服务器端点"):
        _ensure_distinct_database_account(migration_url, application_url)


def test_runner_rejects_migration_target_on_different_mysql_port():
    from app.db.migrations.runner import (
        MigrationRunnerError,
        _ensure_distinct_database_account,
    )
    from sqlalchemy.engine import make_url

    migration_url = make_url(
        "mysql+aiomysql://migration_user:secret@127.0.0.1:3307/platform"
    )
    application_url = (
        "mysql+aiomysql://application_user:secret@127.0.0.1:3306/platform"
    )

    with pytest.raises(MigrationRunnerError, match="同一个 MySQL 服务器端点"):
        _ensure_distinct_database_account(migration_url, application_url)


def test_runner_accepts_same_mysql_host_with_implicit_default_port():
    from app.db.migrations.runner import _ensure_distinct_database_account
    from sqlalchemy.engine import make_url

    migration_url = make_url(
        "mysql+aiomysql://migration_user:secret@DB.INTERNAL/platform"
    )
    application_url = (
        "mysql+aiomysql://application_user:secret@db.internal:3306/platform"
    )

    _ensure_distinct_database_account(migration_url, application_url)

def test_runner_rejects_non_mysql_application_database():
    from app.db.migrations.runner import (
        MigrationRunnerError,
        _ensure_distinct_database_account,
    )
    from sqlalchemy.engine import make_url

    migration_url = make_url(
        "mysql+aiomysql://migration_user:secret@127.0.0.1:3306/platform"
    )
    application_url = "sqlite+aiosqlite:///./platform.db"

    with pytest.raises(MigrationRunnerError, match="应用数据库必须使用 MySQL"):
        _ensure_distinct_database_account(migration_url, application_url)



@pytest.mark.asyncio
async def test_identity_scope_check_constraint_is_enforced_and_migration_is_idempotent(tmp_path: Path):
    """真实 MySQL 验证身份作用域 CHECK 约束拒绝非法组合，并允许安全重跑。"""
    database = _create_database()
    try:
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "sql/migrations/20261113_third_party_report_identity_scope_constraints.sql"
        )
        migration_sql = migration_path.read_text(encoding="utf-8")
        migrations = _write_migrations(
            tmp_path,
            [("20261113_identity_scope_constraints", migration_sql)],
        )
        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE third_party_report_logs ("
                    "id INT NOT NULL PRIMARY KEY AUTO_INCREMENT, "
                    "identity_scope VARCHAR(32) NOT NULL, "
                    "platform VARCHAR(100) NULL"
                    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )
                cursor.executemany(
                    "INSERT INTO third_party_report_logs (identity_scope, platform) VALUES (%s, %s)",
                    [
                        ("legacy_unresolved", None),
                        ("unscoped", None),
                        ("platform_scoped", "meta"),
                    ],
                )

        url = _database_url(database)
        app_url = _application_database_url(database)
        await apply_migrations(
            url,
            application_database_url=app_url,
            repository_root=tmp_path,
            migrations=migrations,
        )
        # 直接重放 SQL，验证 migration 脚本本身可重复执行（不只是 ledger 跳过）。
        from app.db.migrations.sql_parser import split_mysql_statements

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                for statement in split_mysql_statements(migration_sql):
                    cursor.execute(statement)

        # Runner 随后必须根据 ledger 返回空计划，不重复应用 revision。
        assert await apply_migrations(
            url,
            application_database_url=app_url,
            repository_root=tmp_path,
            migrations=migrations,
        ) == ()

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                invalid_rows = [
                    ("unknown_scope", None),
                    ("platform_scoped", None),
                    ("platform_scoped", ""),
                    ("platform_scoped", "   "),
                    ("unscoped", "meta"),
                    ("legacy_unresolved", "meta"),
                ]
                for scope, platform in invalid_rows:
                    with pytest.raises(pymysql.err.OperationalError) as error:
                        cursor.execute(
                            "INSERT INTO third_party_report_logs (identity_scope, platform) VALUES (%s, %s)",
                            (scope, platform),
                        )
                    assert error.value.args[0] == 3819
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                    "WHERE CONSTRAINT_SCHEMA = %s AND TABLE_NAME = 'third_party_report_logs' "
                    "AND CONSTRAINT_NAME = 'chk_third_party_identity_scope_v1' "
                    "AND CONSTRAINT_TYPE = 'CHECK'",
                    (database,),
                )
                assert cursor.fetchone()[0] == 1
    finally:
        _drop_database(database)


@pytest.mark.asyncio
async def test_runner_rejects_ledger_checks_that_are_present_but_semantically_ineffective(
    tmp_path: Path,
):
    """同名 ledger 的 CHECK 名称/关键字齐全但用 OR TRUE 绕过时，Runner 必须拒绝。"""
    database = _create_database()
    try:
        migrations = _write_migrations(
            tmp_path,
            [
                (
                    "20261118_runner_check_guard",
                    "CREATE TABLE must_not_run_when_ledger_checks_are_weak "
                    "(id INT NOT NULL PRIMARY KEY);",
                )
            ],
        )
        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE platform_schema_migrations (
                        revision VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                        checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                        status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                        execution_order INT UNSIGNED NOT NULL,
                        started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        applied_at DATETIME(6) NULL,
                        error_type VARCHAR(128) NULL,
                        PRIMARY KEY (revision),
                        UNIQUE KEY uq_platform_migration_execution_order (execution_order),
                        CONSTRAINT chk_platform_migration_status
                            CHECK (status IN ('running', 'applied', 'failed') OR 1 = 1),
                        CONSTRAINT chk_platform_migration_checksum
                            CHECK (
                                REGEXP_LIKE(checksum COLLATE ascii_bin, '^[0-9a-f]{64}$', 'c')
                                OR 1 = 1
                            ),
                        CONSTRAINT chk_platform_migration_execution_order
                            CHECK (execution_order > 0 OR 1 = 1),
                        CONSTRAINT chk_platform_migration_state_fields
                            CHECK (
                                (status = 'running' AND applied_at IS NULL AND error_type IS NULL)
                                OR (status = 'applied' AND applied_at IS NOT NULL AND error_type IS NULL)
                                OR (status = 'failed' AND applied_at IS NULL AND error_type IS NOT NULL)
                                OR 1 = 1
                            )
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
                    """
                )

        with pytest.raises(MigrationRunnerError, match="CHECK"):
            await apply_migrations(
                _database_url(database),
                application_database_url=_application_database_url(database),
                repository_root=tmp_path,
                migrations=migrations,
            )

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s "
                    "AND TABLE_NAME = 'must_not_run_when_ledger_checks_are_weak'",
                    (database,),
                )
                assert cursor.fetchone()[0] == 0
    finally:
        _drop_database(database)

@pytest.mark.asyncio
async def test_runner_executes_with_database_scoped_migration_least_privileges(
    tmp_path: Path,
):
    """真实 MySQL 验证 Runner 仅凭目标 schema 最小 DDL/DML 权限完成迁移。"""
    database = _create_database()
    external_database = f"platform_ci_mr_ext_{secrets.token_hex(5)}"
    migration_username = f"platform_mr_{secrets.token_hex(8)}"
    migration_password = secrets.token_hex(24)
    root = _root_connect()
    try:
        with root.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{external_database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
            cursor.execute(
                f"CREATE TABLE `{external_database}`.outside_probe "
                "(id INT NOT NULL PRIMARY KEY, value INT NOT NULL) ENGINE=InnoDB"
            )
            cursor.execute(
                f"CREATE USER '{migration_username}'@'%' "
                f"IDENTIFIED BY '{migration_password}'"
            )
            # MySQL ALTER TABLE 还要求 CREATE 和 INSERT；INDEX 单独覆盖索引操作。
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, CREATE, ALTER, INDEX "
                f"ON `{database}`.* TO '{migration_username}'@'%'"
            )

        migrations = _write_migrations(
            tmp_path,
            [
                (
                    "20261119_least_privilege_01_create",
                    "CREATE TABLE migration_privilege_probe ("
                    "id INT NOT NULL PRIMARY KEY, value INT NOT NULL"
                    ") ENGINE=InnoDB;",
                ),
                (
                    "20261119_least_privilege_02_dml",
                    "INSERT INTO migration_privilege_probe (id, value) VALUES (1, 10); "
                    "UPDATE migration_privilege_probe SET value = value + 5 WHERE id = 1;",
                ),
                (
                    "20261119_least_privilege_03_alter_index",
                    "ALTER TABLE migration_privilege_probe "
                    "ADD COLUMN note VARCHAR(32) NULL; "
                    "CREATE INDEX ix_migration_privilege_value "
                    "ON migration_privilege_probe (value); "
                    "ALTER TABLE migration_privilege_probe "
                    "DROP INDEX ix_migration_privilege_value;",
                ),
            ],
        )
        migration_url = URL.create(
            "mysql+aiomysql",
            username=migration_username,
            password=migration_password,
            host=HOST,
            port=PORT,
            database=database,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)
        application_url = _application_database_url(database)

        applied = await apply_migrations(
            migration_url,
            application_database_url=application_url,
            repository_root=tmp_path,
            migrations=migrations,
        )
        assert applied == tuple(item.revision for item in migrations)
        assert await apply_migrations(
            migration_url,
            application_database_url=application_url,
            repository_root=tmp_path,
            migrations=migrations,
        ) == ()

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, value, note FROM migration_privilege_probe"
                )
                assert cursor.fetchall() == ((1, 15, None),)
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA = %s "
                    "AND TABLE_NAME = 'migration_privilege_probe' "
                    "AND INDEX_NAME = 'ix_migration_privilege_value'",
                    (database,),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "SELECT revision, status, execution_order "
                    "FROM platform_schema_migrations ORDER BY execution_order"
                )
                assert cursor.fetchall() == tuple(
                    (item.revision, "applied", index)
                    for index, item in enumerate(migrations, start=1)
                )

        migration_account = pymysql.connect(
            host=HOST,
            port=PORT,
            user=migration_username,
            password=migration_password,
            database=database,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=5,
        )
        try:
            with migration_account.cursor() as cursor:
                cursor.execute("SELECT CURRENT_USER(), DATABASE(), CURRENT_ROLE()")
                identity, selected_database, active_roles = cursor.fetchone()
                assert identity.casefold().startswith(
                    f"{migration_username}@".casefold()
                )
                assert selected_database == database
                assert active_roles == "NONE"

                cursor.execute("SHOW GRANTS")
                grants = [str(row[0]).upper() for row in cursor.fetchall()]
                assert len(grants) == 2, grants
                scoped = [
                    grant
                    for grant in grants
                    if f"`{database}`.*".upper() in grant
                ]
                assert len(scoped) == 1, grants
                privilege_clause = scoped[0].split(" ON ", 1)[0].removeprefix(
                    "GRANT "
                )
                actual_privileges = {
                    item.strip() for item in privilege_clause.split(",")
                }
                assert actual_privileges == {
                    "SELECT",
                    "INSERT",
                    "UPDATE",
                    "CREATE",
                    "ALTER",
                    "INDEX",
                }, grants
                assert "GRANT OPTION" not in " ".join(grants)

                denied_statements = (
                    "DELETE FROM migration_privilege_probe WHERE id = 1",
                    "DROP TABLE migration_privilege_probe",
                    "CREATE DATABASE migration_privilege_database_must_be_denied",
                    f"UPDATE `{external_database}`.outside_probe SET value = value + 1",
                    f"GRANT SELECT ON `{database}`.* "
                    f"TO '{migration_username}'@'%'",
                )
                for statement in denied_statements:
                    with pytest.raises(pymysql.err.OperationalError) as denied:
                        cursor.execute(statement)
                    assert denied.value.args[0] in (1044, 1142), (
                        statement,
                        denied.value.args,
                    )
        finally:
            migration_account.close()
    finally:
        with root.cursor() as cursor:
            cursor.execute(f"DROP USER IF EXISTS '{migration_username}'@'%'")
            cursor.execute(f"DROP DATABASE IF EXISTS `{external_database}`")
            cursor.execute("DROP DATABASE IF EXISTS migration_privilege_database_must_be_denied")
        root.close()
        _drop_database(database)



@pytest.mark.asyncio
async def test_runner_resumes_interrupted_event_key_backfill_in_batches(
    tmp_path: Path, monkeypatch
):
    """真实 MySQL 验证分批提交、running ledger 续跑和幂等回填。"""
    import app.db.migrations.runner as migration_runner

    database = _create_database()
    try:
        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE third_party_report_logs ("
                    "id INT NOT NULL PRIMARY KEY AUTO_INCREMENT, "
                    "source VARCHAR(50) NOT NULL, "
                    "adsid VARCHAR(500) NOT NULL, "
                    "event VARCHAR(50) NOT NULL, "
                    "conversion_id VARCHAR(255) NULL, "
                    "event_key VARCHAR(64) NULL"
                    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )
                cursor.executemany(
                    "INSERT INTO third_party_report_logs "
                    "(source, adsid, event, conversion_id, event_key) "
                    "VALUES (%s, %s, %s, %s, NULL)",
                    [
                        (
                            "meta",
                            f"ad-{index}",
                            "ViewContent" if index % 2 == 0 else "Purchase",
                            f"conversion-{index}",
                        )
                        for index in range(1, 2501)
                    ],
                )

        update_sql = """
        UPDATE third_party_report_logs
        SET event_key = SHA2(
            CONCAT(
                CHAR_LENGTH(source), ':', source,
                CHAR_LENGTH(adsid), ':', adsid,
                CHAR_LENGTH(event), ':', event,
                CHAR_LENGTH(CASE WHEN CAST(event AS BINARY) = CAST('ViewContent' AS BINARY)
                    THEN '' ELSE COALESCE(conversion_id, '') END), ':',
                CASE WHEN CAST(event AS BINARY) = CAST('ViewContent' AS BINARY)
                    THEN '' ELSE COALESCE(conversion_id, '') END
            ),
            256
        )
        WHERE event_key IS NULL;
        """
        migrations = _write_migrations(
            tmp_path,
            [
                (
                    "20261110_event_key_backfill_test",
                    update_sql,
                    "third_party_report_event_key",
                )
            ],
        )
        url = _database_url(database)
        app_url = _application_database_url(database)
        monkeypatch.setattr(migration_runner, "_EVENT_KEY_BACKFILL_BATCH_SIZE", 500)
        original_backfill = migration_runner._run_third_party_report_event_key_backfill

        async def interrupt_after_two_batches(connection):
            summary = await original_backfill(
                connection, batch_size=500, max_batches=2
            )
            assert summary["batches"] == 2
            assert summary["updated_rows"] == 1000
            raise RuntimeError("synthetic batch interruption")

        monkeypatch.setattr(
            migration_runner,
            "_run_third_party_report_event_key_backfill",
            interrupt_after_two_batches,
        )
        with pytest.raises(MigrationExecutionError, match="running"):
            await apply_migrations(
                url,
                application_database_url=app_url,
                repository_root=tmp_path,
                migrations=migrations,
            )

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM third_party_report_logs WHERE event_key IS NOT NULL"
                )
                assert cursor.fetchone()[0] == 1000
                cursor.execute(
                    "SELECT status FROM platform_schema_migrations WHERE revision = %s",
                    (migrations[0].revision,),
                )
                assert cursor.fetchone()[0] == "running"

        # 从 running 状态重新 apply：重扫已完成的 PK 范围，但只更新 NULL 行。
        monkeypatch.setattr(
            migration_runner,
            "_run_third_party_report_event_key_backfill",
            original_backfill,
        )
        assert await apply_migrations(
            url,
            application_database_url=app_url,
            repository_root=tmp_path,
            migrations=migrations,
        ) == (migrations[0].revision,)

        with _root_connect(database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*), COUNT(event_key), COUNT(DISTINCT event_key) "
                    "FROM third_party_report_logs"
                )
                assert cursor.fetchone() == (2500, 2500, 2500)
                cursor.execute(
                    "SELECT event_key FROM third_party_report_logs WHERE id = 1"
                )
                first_event_key = cursor.fetchone()[0]
                expected_payload = "4:meta4:ad-18:ViewContent0:"
                assert first_event_key == hashlib.sha256(
                    expected_payload.encode("utf-8")
                ).hexdigest()
                cursor.execute(
                    "SELECT status FROM platform_schema_migrations WHERE revision = %s",
                    (migrations[0].revision,),
                )
                assert cursor.fetchone()[0] == "applied"

        assert await apply_migrations(
            url,
            application_database_url=app_url,
            repository_root=tmp_path,
            migrations=migrations,
        ) == ()
    finally:
        _drop_database(database)
