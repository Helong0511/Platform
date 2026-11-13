"""MySQL 增量 migration Runner。

仅接受独立 MIGRATION_DATABASE_URL；不读取或回退到应用运行时 DSN。
每条 migration 先持久化 running，再逐条执行并提交；MySQL DDL 隐式提交，
失败时记录 failed/running 并 fail closed，禁止未经人工核验自动重跑部分 DDL。
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrations.ledger import validate_ledger_rows
from app.db.migrations.manifest import Migration, MigrationManifestError, validate_manifest
from app.db.migrations.planner import plan_migrations
from app.db.migrations.sql_parser import MigrationSQLParseError, split_mysql_statements

logger = logging.getLogger(__name__)

_LEDGER_TABLE = "platform_schema_migrations"
_LEDGER_LOCK_PREFIX = "platform_migrations_"
_MIN_MYSQL_VERSION = (8, 0, 16)


class MigrationRunnerError(RuntimeError):
    """迁移执行、连接或物理 ledger schema 不满足安全要求。"""


class MigrationLockUnavailable(MigrationRunnerError):
    """无法取得唯一迁移锁。"""


class MigrationExecutionError(MigrationRunnerError):
    """migration 部分执行失败；必须先人工核验 DDL 状态。"""


_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS platform_schema_migrations (
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
        CHECK (status IN ('running', 'applied', 'failed')),
    CONSTRAINT chk_platform_migration_checksum
        CHECK (REGEXP_LIKE(checksum COLLATE ascii_bin, '^[0-9a-f]{64}$', 'c')),
    CONSTRAINT chk_platform_migration_execution_order
        CHECK (execution_order > 0),
    CONSTRAINT chk_platform_migration_state_fields
        CHECK (
            (status = 'running' AND applied_at IS NULL AND error_type IS NULL)
            OR (status = 'applied' AND applied_at IS NOT NULL AND error_type IS NULL)
            OR (status = 'failed' AND applied_at IS NULL AND error_type IS NOT NULL)
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='平台数据库增量迁移执行账本'
"""


def _migration_lock_name(database_name: str) -> str:
    """稳定且不超过 MySQL GET_LOCK 64 字符上限的数据库级锁名。"""
    digest = hashlib.sha256(database_name.encode("utf-8")).hexdigest()[:32]
    return f"{_LEDGER_LOCK_PREFIX}{digest}"


def _parse_mysql_version(value: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value or "")
    if not match:
        raise MigrationRunnerError("无法识别 MySQL Server 版本")
    return tuple(int(part) for part in match.groups())


def _ensure_distinct_database_account(migration_url, application_database_url: str | None) -> None:
    """同一 MySQL endpoint/database 不允许复用应用运行账号执行 DDL。"""
    if not application_database_url:
        return
    app_url = make_url(application_database_url)
    if app_url.get_backend_name() != "mysql":
        return
    same_server = (
        migration_url.host == app_url.host
        and (migration_url.port or 3306) == (app_url.port or 3306)
    )
    if same_server and migration_url.username == app_url.username:
        raise MigrationRunnerError(
            "迁移 DSN 必须使用独立于应用运行账号的 MySQL 用户"
        )


async def _consume_result(connection, statement: str) -> None:
    result = await connection.exec_driver_sql(statement)
    try:
        if result.returns_rows:
            # migration 中的 SELECT / 动态 SQL 结果必须消费，避免连接残留未读结果集。
            result.fetchall()
    finally:
        result.close()
    # DDL 会隐式提交；显式 commit 也为 DML 和会话状态提供清晰边界。
    await connection.commit()


async def _ensure_ledger_schema(connection) -> None:
    await connection.exec_driver_sql(_LEDGER_DDL)
    await connection.commit()

    table = (
        await connection.execute(
            text(
                "SELECT ENGINE, TABLE_COLLATION FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
            ),
            {"table_name": _LEDGER_TABLE},
        )
    ).mappings().one_or_none()
    if (
        table is None
        or table["ENGINE"] != "InnoDB"
        or table["TABLE_COLLATION"] != "utf8mb4_0900_ai_ci"
    ):
        raise MigrationRunnerError("migration ledger 表引擎或 collation 不符合要求")

    column_rows = (
        await connection.execute(
            text(
                "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
                "CHARACTER_SET_NAME, COLLATION_NAME "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
            ),
            {"table_name": _LEDGER_TABLE},
        )
    ).mappings().all()
    columns = {row["COLUMN_NAME"]: row for row in column_rows}
    expected_columns = {
        "revision": ("varchar(64)", "NO", "ascii", "ascii_bin"),
        "checksum": ("char(64)", "NO", "ascii", "ascii_bin"),
        "status": ("varchar(16)", "NO", "ascii", "ascii_bin"),
        "execution_order": ("int unsigned", "NO", None, None),
        "started_at": ("datetime(6)", "NO", None, None),
        "applied_at": ("datetime(6)", "YES", None, None),
        "error_type": ("varchar(128)", "YES", "utf8mb4", "utf8mb4_0900_ai_ci"),
    }
    if set(columns) != set(expected_columns):
        raise MigrationRunnerError("migration ledger 列集合不符合预期")
    for name, (column_type, nullable, charset, collation) in expected_columns.items():
        row = columns[name]
        if (
            row["COLUMN_TYPE"].lower() != column_type
            or row["IS_NULLABLE"] != nullable
            or (charset is not None and row["CHARACTER_SET_NAME"] != charset)
            or (collation is not None and row["COLLATION_NAME"] != collation)
        ):
            raise MigrationRunnerError(f"migration ledger 字段定义错误：{name}")

    index_rows = (
        await connection.execute(
            text(
                "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name "
                "ORDER BY INDEX_NAME, SEQ_IN_INDEX"
            ),
            {"table_name": _LEDGER_TABLE},
        )
    ).mappings().all()
    indexes: dict[str, list[tuple[int, str, int]]] = {}
    for row in index_rows:
        indexes.setdefault(row["INDEX_NAME"], []).append(
            (int(row["SEQ_IN_INDEX"]), row["COLUMN_NAME"], int(row["NON_UNIQUE"]))
        )
    if set(indexes) != {"PRIMARY", "uq_platform_migration_execution_order"}:
        raise MigrationRunnerError("migration ledger 索引集合不符合预期")
    if indexes["PRIMARY"] != [(1, "revision", 0)]:
        raise MigrationRunnerError("migration ledger 主键定义错误")
    if indexes["uq_platform_migration_execution_order"] != [
        (1, "execution_order", 0)
    ]:
        raise MigrationRunnerError("migration ledger execution_order 唯一索引定义错误")

    check_rows = (
        await connection.execute(
            text(
                "SELECT tc.CONSTRAINT_NAME, tc.ENFORCED, cc.CHECK_CLAUSE "
                "FROM information_schema.TABLE_CONSTRAINTS tc "
                "JOIN information_schema.CHECK_CONSTRAINTS cc "
                "ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA "
                "AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME "
                "WHERE tc.CONSTRAINT_SCHEMA = DATABASE() "
                "AND tc.TABLE_NAME = :table_name AND tc.CONSTRAINT_TYPE = 'CHECK'"
            ),
            {"table_name": _LEDGER_TABLE},
        )
    ).mappings().all()
    checks = {row["CONSTRAINT_NAME"]: row for row in check_rows}
    expected_checks = {
        "chk_platform_migration_status",
        "chk_platform_migration_checksum",
        "chk_platform_migration_execution_order",
        "chk_platform_migration_state_fields",
    }
    if (
        set(checks) != expected_checks
        or any(row["ENFORCED"] != "YES" for row in checks.values())
    ):
        raise MigrationRunnerError("migration ledger CHECK 约束缺失或未强制执行")
    clauses = {name: str(row["CHECK_CLAUSE"]).lower() for name, row in checks.items()}
    if (
        "running" not in clauses["chk_platform_migration_status"]
        or "applied" not in clauses["chk_platform_migration_status"]
        or "failed" not in clauses["chk_platform_migration_status"]
        or "regexp_like" not in clauses["chk_platform_migration_checksum"]
        or "[0-9a-f]" not in clauses["chk_platform_migration_checksum"]
        or "{64}" not in clauses["chk_platform_migration_checksum"]
        or "execution_order" not in clauses["chk_platform_migration_execution_order"]
        or "applied_at" not in clauses["chk_platform_migration_state_fields"]
        or "error_type" not in clauses["chk_platform_migration_state_fields"]
    ):
        raise MigrationRunnerError("migration ledger CHECK 约束定义错误")


async def _apply_with_locked_connection(
    connection,
    *,
    database_name: str,
    root: Path,
    manifest: tuple[Migration, ...],
    lock_timeout: int,
) -> tuple[str, ...]:
    lock_name = _migration_lock_name(database_name)
    lock_result = await connection.execute(
        text("SELECT GET_LOCK(:lock_name, :timeout)"),
        {"lock_name": lock_name, "timeout": lock_timeout},
    )
    if lock_result.scalar_one_or_none() != 1:
        raise MigrationLockUnavailable("无法取得数据库 migration GET_LOCK")
    await connection.commit()

    try:
        session_info = (
            await connection.execute(
                text(
                    "SELECT VERSION() AS server_version, DATABASE() AS database_name, "
                    "@@SESSION.sql_mode AS sql_mode, "
                    "@@character_set_connection AS connection_charset"
                )
            )
        ).mappings().one()
        if session_info["database_name"] != database_name:
            raise MigrationRunnerError("连接实际数据库与迁移 DSN 指定数据库不一致")
        if _parse_mysql_version(session_info["server_version"]) < _MIN_MYSQL_VERSION:
            raise MigrationRunnerError("Runner 要求 MySQL 8.0.16 或更高版本")
        if session_info["connection_charset"].lower() != "utf8mb4":
            raise MigrationRunnerError("migration 连接字符集必须为 utf8mb4")

        sql_mode = {
            item.strip().upper()
            for item in (session_info["sql_mode"] or "").split(",")
            if item.strip()
        }
        backslash_escapes = "NO_BACKSLASH_ESCAPES" not in sql_mode
        parsed: dict[str, tuple[str, ...]] = {}
        for migration in manifest:
            sql = (root / migration.path).read_text(encoding="utf-8")
            parsed[migration.revision] = split_mysql_statements(
                sql, backslash_escapes=backslash_escapes
            )
            if not parsed[migration.revision]:
                raise MigrationRunnerError(
                    f"migration 没有可执行 SQL：{migration.revision}"
                )

        await _ensure_ledger_schema(connection)
        raw_rows = (
            await connection.execute(
                text(
                    "SELECT revision, checksum, status, execution_order "
                    "FROM platform_schema_migrations ORDER BY execution_order"
                )
            )
        ).mappings().all()
        applied_checksums = validate_ledger_rows(
            raw_rows,
            repository_root=root,
            migrations=manifest,
        )
        pending = plan_migrations(
            applied_checksums,
            repository_root=root,
            migrations=manifest,
        )

        completed: list[str] = []
        for migration in pending:
            execution_order = len(applied_checksums) + 1
            await connection.execute(
                text(
                    "INSERT INTO platform_schema_migrations "
                    "(revision, checksum, status, execution_order) "
                    "VALUES (:revision, :checksum, 'running', :execution_order)"
                ),
                {
                    "revision": migration.revision,
                    "checksum": migration.sha256,
                    "execution_order": execution_order,
                },
            )
            await connection.commit()

            try:
                for statement in parsed[migration.revision]:
                    await _consume_result(connection, statement)
                result = await connection.execute(
                    text(
                        "UPDATE platform_schema_migrations "
                        "SET status = 'applied', applied_at = CURRENT_TIMESTAMP(6), "
                        "error_type = NULL WHERE revision = :revision AND status = 'running'"
                    ),
                    {"revision": migration.revision},
                )
                if (result.rowcount or 0) != 1:
                    raise MigrationRunnerError(
                        f"migration ledger 状态转换失败：{migration.revision}"
                    )
                await connection.commit()
            except Exception as exc:
                # COMMIT ACK 可能丢失；先读 ledger 判断 applied 是否实际已提交。
                try:
                    await connection.rollback()
                    current_status = await connection.scalar(
                        text(
                            "SELECT status FROM platform_schema_migrations "
                            "WHERE revision = :revision"
                        ),
                        {"revision": migration.revision},
                    )
                    if current_status == "applied":
                        applied_checksums[migration.revision] = migration.sha256
                        completed.append(migration.revision)
                        continue
                    result = await connection.execute(
                        text(
                            "UPDATE platform_schema_migrations "
                            "SET status = 'failed', error_type = :error_type "
                            "WHERE revision = :revision AND status = 'running'"
                        ),
                        {
                            "revision": migration.revision,
                            "error_type": type(exc).__name__[:128],
                        },
                    )
                    if (result.rowcount or 0) == 1:
                        await connection.commit()
                    else:
                        await connection.rollback()
                except Exception:
                    # 连接中断时保留 running 墓碑；下一次 apply 会 fail closed。
                    logger.error(
                        "Migration 失败状态无法回写；ledger 保留 running：revision=%s",
                        migration.revision,
                    )
                raise MigrationExecutionError(
                    f"migration 执行失败：{migration.revision}；"
                    "MySQL DDL 可能部分提交，必须先人工核验再恢复"
                ) from exc

            applied_checksums[migration.revision] = migration.sha256
            completed.append(migration.revision)
        return tuple(completed)
    finally:
        # GET_LOCK 是 session lock，不随 COMMIT/ROLLBACK 释放；必须在同一连接显式释放。
        try:
            released = await connection.scalar(
                text("SELECT RELEASE_LOCK(:lock_name)"),
                {"lock_name": lock_name},
            )
            await connection.commit()
            if released != 1:
                logger.error("Migration GET_LOCK 未能显式释放；连接关闭将释放会话锁")
        except Exception as exc:
            logger.warning(
                "Migration GET_LOCK 释放异常；连接关闭将释放会话锁：exception_type=%s",
                type(exc).__name__,
            )


async def apply_migrations(
    database_url: str,
    *,
    application_database_url: str,
    repository_root: str | Path | None = None,
    migrations: tuple[Migration, ...] | None = None,
    lock_timeout: int = 60,
) -> tuple[str, ...]:
    """使用独立 MySQL DSN 执行 manifest 中尚未应用的 migration。

    一个 AsyncConnection 从 GET_LOCK 到 RELEASE_LOCK 全程保持 checkout；
    不使用 ORM Session，不允许连接池在迁移期间换用另一个物理连接。
    """
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("必须显式提供 MIGRATION_DATABASE_URL")
    if not isinstance(application_database_url, str) or not application_database_url.strip():
        raise ValueError("必须提供应用数据库 DSN，以验证迁移账号与运行账号分离")
    if not isinstance(lock_timeout, int) or not 0 <= lock_timeout <= 600:
        raise ValueError("lock_timeout 必须在 0 到 600 秒之间")

    url = make_url(database_url)
    if url.get_backend_name() != "mysql" or url.drivername != "mysql+aiomysql":
        raise MigrationRunnerError("Runner 仅接受 mysql+aiomysql 独立迁移 DSN")
    if not url.database:
        raise MigrationRunnerError("迁移 DSN 必须明确指定数据库名")
    _ensure_distinct_database_account(url, application_database_url)

    root = Path(repository_root).resolve() if repository_root else Path(__file__).resolve().parents[3]
    manifest = validate_manifest(root, migrations)
    engine = create_async_engine(url, echo=False, pool_pre_ping=False)
    try:
        async with engine.connect() as connection:
            # 在同一物理连接中取得锁、执行所有 DDL 并释放锁。
            await connection.exec_driver_sql("SET NAMES utf8mb4")
            await connection.commit()
            return await _apply_with_locked_connection(
                connection,
                database_name=url.database,
                root=root,
                manifest=manifest,
                lock_timeout=lock_timeout,
            )
    except (MigrationRunnerError, MigrationManifestError, MigrationSQLParseError):
        raise
    except Exception as exc:
        logger.error("Migration Runner 失败：exception_type=%s", type(exc).__name__)
        raise MigrationRunnerError(
            f"Migration Runner 失败：exception_type={type(exc).__name__}"
        ) from exc
    finally:
        await engine.dispose()
