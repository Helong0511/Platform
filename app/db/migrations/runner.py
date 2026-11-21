"""MySQL 增量 migration Runner。

仅接受独立 MIGRATION_DATABASE_URL；不读取或回退到应用运行时 DSN。
每条 migration 先持久化 running，再逐条执行并提交；MySQL DDL 隐式提交，
普通迁移失败后 fail closed；只有 manifest 明确登记的分批回填允许从 running 状态安全续跑。
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
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
_EVENT_KEY_BACKFILL_HANDLER = "third_party_report_event_key"
_EVENT_KEY_BACKFILL_BATCH_SIZE = 1000


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


def _mysql_endpoint_identity(url) -> tuple[str, str, int | None]:
    """提取不含凭据的 MySQL 连接端点；Socket 连接优先于 TCP host/port。"""
    socket = url.query.get("unix_socket")
    if isinstance(socket, (tuple, list)):
        socket = socket[0] if socket else None
    if socket:
        return ("unix_socket", str(socket).strip(), None)
    host = (url.host or "").strip().rstrip(".").casefold()
    port = int(url.port or 3306)
    if not host:
        raise MigrationRunnerError("MySQL DSN 必须明确指定主机或 Unix Socket")
    return ("tcp", host, port)


def _ensure_distinct_database_account(migration_url, application_database_url: str | None) -> None:
    """迁移与应用必须指向同一 MySQL endpoint/database，且使用不同账号。"""
    if not application_database_url:
        return
    app_url = make_url(application_database_url)
    if app_url.get_backend_name() != "mysql":
        raise MigrationRunnerError(
            "应用数据库必须使用 MySQL；拒绝跨数据库类型执行 MySQL migration"
        )
    if not app_url.database:
        raise MigrationRunnerError("应用数据库 DSN 必须明确指定数据库名")
    if migration_url.database != app_url.database:
        raise MigrationRunnerError(
            "迁移 DSN 与应用数据库 DSN 必须指向同一个数据库名"
        )
    if _mysql_endpoint_identity(migration_url) != _mysql_endpoint_identity(app_url):
        raise MigrationRunnerError(
            "迁移 DSN 与应用数据库 DSN 必须指向同一个 MySQL 服务器端点"
        )
    if migration_url.username == app_url.username:
        raise MigrationRunnerError(
            "迁移 DSN 必须使用独立于应用运行账号的 MySQL 用户"
        )


async def _ensure_connected_database_account_separation(
    migration_connection, application_database_url: str
) -> None:
    """比较 MySQL 服务端认证身份，防止不同 DSN 用户名映射到同一账号。"""
    migration_identity = await migration_connection.scalar(
        text("SELECT CURRENT_USER()")
    )
    migration_database = await migration_connection.scalar(text("SELECT DATABASE()"))
    application_engine = create_async_engine(
        make_url(application_database_url), echo=False, pool_pre_ping=False
    )
    try:
        async with application_engine.connect() as application_connection:
            application_identity = await application_connection.scalar(
                text("SELECT CURRENT_USER()")
            )
            application_database = await application_connection.scalar(
                text("SELECT DATABASE()")
            )
        if migration_database != application_database:
            raise MigrationRunnerError(
                "迁移连接与应用连接实际选择的数据库不一致"
            )
        if (
            not isinstance(migration_identity, str)
            or not isinstance(application_identity, str)
            or migration_identity.casefold() == application_identity.casefold()
        ):
            raise MigrationRunnerError(
                "迁移连接与应用连接解析为相同或无法确认的 MySQL 服务端账号"
            )
    finally:
        await application_engine.dispose()


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



def _normalized_event_key_statement(statement: str) -> str:
    return re.sub(r"\s+", " ", statement).strip().casefold().rstrip(";")


def _is_event_key_backfill_statement(statement: str) -> bool:
    """只匹配 checksum 固定的历史迁移中的 event_key 全表 UPDATE。"""
    normalized = _normalized_event_key_statement(statement)
    return (
        normalized.startswith(
            "update third_party_report_logs set event_key = sha2("
        )
        and re.search(r"\bwhere event_key is null$", normalized) is not None
    )


def _is_event_key_missing_check_statement(statement: str) -> bool:
    normalized = _normalized_event_key_statement(statement)
    return normalized.startswith(
        "select count(*) as missing_event_keys from third_party_report_logs"
    ) and "where event_key is null or event_key = ''" in normalized


def _is_event_key_duplicate_check_statement(statement: str) -> bool:
    normalized = _normalized_event_key_statement(statement)
    return (
        normalized.startswith(
            "select event_key, count(*) as duplicate_count from third_party_report_logs"
        )
        and "group by event_key having count(*) > 1" in normalized
    )


async def _run_third_party_report_event_key_backfill(
    connection,
    *,
    batch_size: int | None = None,
    max_batches: int | None = None,
) -> dict[str, int]:
    """按主键范围分批回填并逐批提交；从 id=0 重扫也能安全跳过已完成行。"""
    if batch_size is None:
        batch_size = _EVENT_KEY_BACKFILL_BATCH_SIZE
    if type(batch_size) is not int or not 1 <= batch_size <= 10_000:
        raise ValueError("event_key backfill batch_size must be between 1 and 10000")
    if max_batches is not None and (
        type(max_batches) is not int or max_batches < 1
    ):
        raise ValueError("max_batches must be a positive integer when provided")

    minimum_result = await connection.execute(
        text("SELECT MIN(id) FROM third_party_report_logs")
    )
    try:
        minimum_id = minimum_result.scalar_one_or_none()
    finally:
        minimum_result.close()
    if minimum_id is None:
        await connection.commit()
        return {"batches": 0, "scanned_rows": 0, "updated_rows": 0, "last_id": 0}

    last_id = int(minimum_id) - 1
    scanned_rows = 0
    updated_rows = 0
    batches = 0
    update_sql = text(
        """
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
        WHERE id > :last_id AND id <= :upper_id AND (event_key IS NULL OR event_key = '')
        """
    )

    while True:
        result = await connection.execute(
            text(
                "SELECT id FROM third_party_report_logs "
                "WHERE id > :last_id ORDER BY id LIMIT :batch_size"
            ),
            {"last_id": last_id, "batch_size": batch_size},
        )
        try:
            batch_ids = result.scalars().all()
        finally:
            result.close()

        if not batch_ids:
            await connection.commit()
            break

        upper_id = int(batch_ids[-1])
        update_result = await connection.execute(
            update_sql,
            {"last_id": last_id, "upper_id": upper_id},
        )
        try:
            affected = max(int(update_result.rowcount or 0), 0)
        finally:
            update_result.close()
        await connection.commit()

        scanned_rows += len(batch_ids)
        updated_rows += affected
        batches += 1
        last_id = upper_id

        if batches == 1 or batches % 10 == 0:
            logger.info(
                "Migration event_key batch progress: batches=%s scanned=%s updated=%s last_id=%s",
                batches,
                scanned_rows,
                updated_rows,
                last_id,
            )
        if max_batches is not None and batches >= max_batches:
            break

    logger.info(
        "Migration event_key batch backfill finished: batches=%s scanned=%s updated=%s",
        batches,
        scanned_rows,
        updated_rows,
    )
    return {
        "batches": batches,
        "scanned_rows": scanned_rows,
        "updated_rows": updated_rows,
        "last_id": last_id,
    }


async def _execute_migration_statements(
    connection, migration: Migration, statements: tuple[str, ...]
) -> None:
    """执行 SQL；显式登记的 backfill handler 替换对应全表 UPDATE。"""
    if migration.backfill_handler is None:
        for statement in statements:
            await _consume_result(connection, statement)
        return

    if migration.backfill_handler != _EVENT_KEY_BACKFILL_HANDLER:
        raise MigrationRunnerError(
            f"不支持的 migration backfill handler：{migration.backfill_handler}"
        )

    matched = 0
    for statement in statements:
        if _is_event_key_backfill_statement(statement):
            matched += 1
            if matched > 1:
                raise MigrationRunnerError("event_key backfill SQL 出现重复目标语句")
            summary = await _run_third_party_report_event_key_backfill(connection)
            logger.info(
                "Migration backfill handler completed: revision=%s batches=%s updated=%s",
                migration.revision,
                summary["batches"],
                summary["updated_rows"],
            )
        elif _is_event_key_missing_check_statement(statement):
            result = await connection.exec_driver_sql(statement)
            try:
                missing_count = int(result.scalar_one())
            finally:
                result.close()
            await connection.commit()
            if missing_count:
                raise MigrationRunnerError(
                    f"event_key 回填后仍有 {missing_count} 条 NULL/空值，拒绝继续 DDL"
                )
        elif _is_event_key_duplicate_check_statement(statement):
            result = await connection.exec_driver_sql(statement)
            try:
                duplicate_row = result.fetchone()
            finally:
                result.close()
            await connection.commit()
            if duplicate_row is not None:
                raise MigrationRunnerError(
                    "event_key 回填后发现重复事件键，拒绝创建唯一索引"
                )
        else:
            await _consume_result(connection, statement)

    if matched != 1:
        raise MigrationRunnerError(
            "manifest 声明的 event_key backfill SQL 未唯一匹配；拒绝执行未分批 UPDATE"
        )


async def _verify_ledger_check_semantics(connection) -> None:
    """通过可回滚的真实 INSERT 探针验证 ledger CHECK 约束确实拒绝非法状态。"""
    max_order = int(
        await connection.scalar(
            text("SELECT COALESCE(MAX(execution_order), 0) FROM platform_schema_migrations")
        )
        or 0
    )
    if max_order > 4_294_967_291:
        raise MigrationRunnerError(
            "migration ledger execution_order 已接近无符号上限，无法安全执行约束探针"
        )

    revision_prefix = f"__ledger_check_probe_{uuid.uuid4().hex[:12]}"
    valid_checksum = "a" * 64
    probes = (
        (
            "status",
            f"{revision_prefix}_status",
            valid_checksum,
            "invalid_status",
            max_order + 1,
            None,
            None,
        ),
        (
            "checksum",
            f"{revision_prefix}_checksum",
            "not-a-sha256",
            "running",
            max_order + 2,
            None,
            None,
        ),
        (
            "execution_order",
            f"{revision_prefix}_order",
            valid_checksum,
            "running",
            0,
            None,
            None,
        ),
        (
            "state_fields",
            f"{revision_prefix}_state",
            valid_checksum,
            "applied",
            max_order + 3,
            None,
            None,
        ),
    )

    insert_sql = text(
        "INSERT INTO platform_schema_migrations "
        "(revision, checksum, status, execution_order, applied_at, error_type) "
        "VALUES (:revision, :checksum, :status, :execution_order, :applied_at, :error_type)"
    )
    for name, revision, checksum, status, execution_order, applied_at, error_type in probes:
        savepoint = await connection.begin_nested()
        try:
            try:
                await connection.execute(
                    insert_sql,
                    {
                        "revision": revision,
                        "checksum": checksum,
                        "status": status,
                        "execution_order": execution_order,
                        "applied_at": applied_at,
                        "error_type": error_type,
                    },
                )
            except Exception as exc:
                await savepoint.rollback()
                original = getattr(exc, "orig", None)
                args = getattr(original, "args", ()) or ()
                if not args or args[0] != 3819:
                    raise MigrationRunnerError(
                        f"无法确认 migration ledger CHECK 约束有效：{name}"
                    ) from exc
            else:
                await savepoint.rollback()
                raise MigrationRunnerError(
                    f"migration ledger CHECK 约束未拒绝非法数据：{name}"
                )
        except Exception:
            if savepoint.is_active:
                await savepoint.rollback()
            raise


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

    # 只检查 CHECK_CLAUSE 的文本片段不足以证明约束有效；例如 OR 1=1
    # 可以保留所有关键字却让条件恒真。使用 SAVEPOINT 探针验证真实拒绝行为。
    await _verify_ledger_check_semantics(connection)


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
        resumable_running_revisions = {
            item.revision for item in manifest if item.backfill_handler is not None
        }
        applied_checksums = validate_ledger_rows(
            raw_rows,
            repository_root=root,
            migrations=manifest,
            allow_running_revisions=resumable_running_revisions,
        )
        running_rows = {
            row["revision"]: row for row in raw_rows if row["status"] == "running"
        }
        pending = plan_migrations(
            applied_checksums,
            repository_root=root,
            migrations=manifest,
        )

        completed: list[str] = []
        for migration in pending:
            execution_order = len(applied_checksums) + 1
            existing_running = running_rows.get(migration.revision)
            if existing_running is not None:
                if (
                    migration.backfill_handler is None
                    or existing_running["checksum"] != migration.sha256
                    or existing_running["execution_order"] != execution_order
                ):
                    raise MigrationRunnerError(
                        f"running migration 不满足安全续跑条件：{migration.revision}"
                    )
                # running 只允许 manifest 显式登记的分批回填；保留原账本行并从批次游标安全重扫。
                await connection.commit()
            else:
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
                await _execute_migration_statements(
                    connection, migration, parsed[migration.revision]
                )
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
                try:
                    await connection.rollback()
                    current_status = await connection.scalar(
                        text(
                            "SELECT status FROM platform_schema_migrations "
                            "WHERE revision = :revision"
                        ),
                        {"revision": migration.revision},
                    )
                except Exception:
                    logger.error(
                        "Migration 状态核验失败，保留现有 ledger 状态：%s",
                        migration.revision,
                        exc_info=True,
                    )
                    current_status = None

                # COMMIT ACK 丢失时，数据库可能已经提交 applied；以 ledger 为准。
                if current_status == "applied":
                    applied_checksums[migration.revision] = migration.sha256
                    completed.append(migration.revision)
                    continue

                if (
                    migration.backfill_handler is not None
                    and current_status == "running"
                ):
                    logger.warning(
                        "Resumable migration interrupted; keep running ledger for next apply: revision=%s error_type=%s",
                        migration.revision,
                        type(exc).__name__,
                    )
                    await connection.rollback()
                    raise MigrationExecutionError(
                        f"分批迁移中断，账本保留 running；确认写入方已停止后可安全续跑：{migration.revision}"
                    ) from exc

                try:
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
                    if result.rowcount == 1:
                        await connection.commit()
                    else:
                        await connection.rollback()
                except Exception:
                    logger.error(
                        "Migration 失败状态无法回写，ledger 可能仍为 running：%s",
                        migration.revision,
                        exc_info=True,
                    )
                raise MigrationExecutionError(
                    f"迁移执行失败，账本状态已标记或保留为 failed/running：{migration.revision}"
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


async def read_migration_status(
    database_url: str,
    *,
    application_database_url: str,
) -> tuple[dict, ...]:
    """只读返回 migration ledger；不创建表、不取得 DDL 锁、不修改状态。"""
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("必须显式提供 MIGRATION_DATABASE_URL")
    if not isinstance(application_database_url, str) or not application_database_url.strip():
        raise ValueError("必须提供应用数据库 DSN，以验证迁移账号与运行账号分离")
    url = make_url(database_url)
    if url.get_backend_name() != "mysql" or url.drivername != "mysql+aiomysql":
        raise MigrationRunnerError("Runner 仅接受 mysql+aiomysql 独立迁移 DSN")
    if not url.database:
        raise MigrationRunnerError("迁移 DSN 必须明确指定数据库名")
    _ensure_distinct_database_account(url, application_database_url)

    engine = create_async_engine(url, echo=False, pool_pre_ping=False)
    try:
        async with engine.connect() as connection:
            await _ensure_connected_database_account_separation(
                connection, application_database_url
            )
            database_name = await connection.scalar(text("SELECT DATABASE()"))
            if database_name != url.database:
                raise MigrationRunnerError("连接实际数据库与迁移 DSN 指定数据库不一致")
            exists = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
                ),
                {"table_name": _LEDGER_TABLE},
            )
            if not exists:
                return ()
            rows = (
                await connection.execute(
                    text(
                        "SELECT revision, checksum, status, execution_order, "
                        "started_at, applied_at, error_type "
                        "FROM platform_schema_migrations ORDER BY execution_order"
                    )
                )
            ).mappings().all()
            return tuple(dict(row) for row in rows)
    except MigrationRunnerError:
        raise
    except Exception as exc:
        logger.error("Migration ledger status 查询失败：exception_type=%s", type(exc).__name__)
        raise MigrationRunnerError(
            f"Migration ledger status 查询失败：exception_type={type(exc).__name__}"
        ) from exc
    finally:
        await engine.dispose()


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
            # 用服务端认证身份复核 DSN，避免代理/映射账号绕过静态用户名检查。
            await _ensure_connected_database_account_separation(
                connection, application_database_url
            )
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
