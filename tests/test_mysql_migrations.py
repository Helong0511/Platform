"""MySQL 8.0 隔离迁移集成测试。

只连接 CI 显式注入的临时 MySQL 服务；未配置时跳过。
禁止从应用生产配置读取数据库连接串。
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
from pathlib import Path

import pytest
import pymysql
import threading
from concurrent.futures import ThreadPoolExecutor

from app.db.migrations.sql_parser import split_mysql_statements


HOST = os.getenv("MYSQL_INTEGRATION_HOST")
DATABASE = os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci")
_DESTRUCTIVE_TESTS_ENABLED = os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"


def _is_loopback_host(host: str | None) -> bool:
    """只允许本机隔离 MySQL；禁止迁移测试误连远程/生产数据库。"""
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

# CI 若显式开启了测试模式却未满足隔离条件，直接失败而不是静默跳过，
# 防止错误配置导致破坏性迁移测试连向非测试数据库。
if (os.getenv("GITHUB_ACTIONS") == "true" or (os.getenv("UNIT_TEST") == "1" and HOST)) and not _SAFE_MYSQL_CI:
    raise RuntimeError(
        "拒绝执行破坏性 MySQL 迁移测试：必须使用 loopback 主机、platform_ci 数据库，"
        "并显式设置 MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS=1"
    )

pytestmark = pytest.mark.skipif(
    not _SAFE_MYSQL_CI,
    reason="仅在 GitHub Actions 临时 MySQL 服务中运行破坏性迁移测试",
)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("localhost", True),
        ("mysql", False),
        ("192.0.2.10", False),
        ("", False),
        (None, False),
    ],
)
def test_destructive_mysql_guard_only_accepts_loopback_hosts(host, expected):
    assert _is_loopback_host(host) is expected


def _connect():
    return pymysql.connect(
        host=HOST,
        port=int(os.getenv("MYSQL_INTEGRATION_PORT", "3306")),
        user=os.getenv("MYSQL_INTEGRATION_USER", "root"),
        password=os.getenv("MYSQL_INTEGRATION_PASSWORD", ""),
        database=os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci"),
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )


def _run_sql_file(cursor, relative_path: str) -> None:
    sql = Path(relative_path).read_text(encoding="utf-8")
    # 集成测试与离线校验共用同一 SQL 解析器，避免测试使用简单 split(';')
    # 而掩盖字符串分号、块注释或 SQL_MODE 转义规则导致的生产执行差异。
    statements = split_mysql_statements(sql)
    for statement in statements:
        cursor.execute(statement)
        if cursor.description:
            cursor.fetchall()


def _index_columns(cursor, table_name: str, index_name: str) -> list[str]:
    """读取隔离 MySQL 索引的真实列顺序，避免只检查索引名称而漏掉 schema drift。"""
    allowed_tables = {"third_party_report_logs", "postback_forward_logs"}
    if table_name not in allowed_tables:
        raise ValueError("unexpected migration test table")
    cursor.execute(f"SHOW INDEX FROM `{table_name}` WHERE Key_name = %s", (index_name,))
    rows = cursor.fetchall()
    return [
        row[4]
        for row in sorted(rows, key=lambda item: item[3])
    ]


def _column_metadata(cursor, table_name: str, column_name: str):
    """读取字段类型、NULL 和默认值，核对迁移结果而不只核对字段名。"""
    allowed_tables = {"third_party_report_logs", "postback_forward_logs"}
    if table_name not in allowed_tables:
        raise ValueError("unexpected migration test table")
    cursor.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE %s", (column_name,))
    return cursor.fetchone()


def _event_key(source: str, adsid: str, event: str, conversion_id: str | None) -> str:
    # 必须与应用和 SQL migration 的身份规则一致：ViewContent 的 conversion_id
    # 可能由后续 Purchase 补写，仅用于关联，不属于 ViewContent 的幂等身份。
    identity_conversion_id = "" if event == "ViewContent" else (conversion_id or "")
    parts = (source or "", adsid or "", event or "", identity_conversion_id)
    identity = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def test_event_key_migration_preserves_legacy_unique_index_when_new_key_collides():
    """新事件键碰撞时迁移失败，但旧唯一约束必须继续保护在线数据。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute(
                """
                CREATE TABLE third_party_report_logs (
                    id INT NOT NULL AUTO_INCREMENT,
                    source VARCHAR(50) NOT NULL,
                    adsid VARCHAR(500) NOT NULL,
                    event VARCHAR(50) NOT NULL,
                    conversion_id VARCHAR(255) NULL,
                    event_key VARCHAR(64) NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY unique_source_adsid (source, adsid)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            collision_key = hashlib.sha256(b"synthetic-event-key-collision").hexdigest()
            cursor.executemany(
                "INSERT INTO third_party_report_logs "
                "(source, adsid, event, conversion_id, event_key) "
                "VALUES (%s, %s, %s, %s, %s)",
                [
                    ("source-a", "ad-a", "Purchase", "conv-a", collision_key),
                    ("source-b", "ad-b", "Purchase", "conv-b", collision_key),
                ],
            )

            with pytest.raises(pymysql.err.IntegrityError):
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261110_third_party_report_event_idempotency.sql",
                )

            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            index_names = {row[2] for row in cursor.fetchall()}
            assert "unique_source_adsid" in index_names
            assert "unique_event_key" not in index_names
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()


def test_event_migration_rejects_wrong_same_name_index_without_dropping_legacy_unique():
    """同名但错误的 event 索引必须阻断迁移，保留旧唯一约束，防止静默失去保护。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute(
                "CREATE TABLE third_party_report_logs ("
                "id INT NOT NULL AUTO_INCREMENT, source VARCHAR(50) NOT NULL, "
                "adsid VARCHAR(500) NOT NULL, event VARCHAR(50) NOT NULL, "
                "conversion_id VARCHAR(255) NULL, PRIMARY KEY (id), "
                "UNIQUE KEY unique_source_adsid (source, adsid), "
                "KEY unique_event_key (event)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            with pytest.raises(pymysql.err.OperationalError) as migration_error:
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261110_third_party_report_event_idempotency.sql",
                )
            assert migration_error.value.args[0] == 1061
            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            indexes = cursor.fetchall()
            index_names = {row[2] for row in indexes}
            assert "unique_source_adsid" in index_names
            assert "unique_event_key" in index_names
            wrong_index_columns = [row[4] for row in indexes if row[2] == "unique_event_key"]
            assert wrong_index_columns == ["event"]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()

def test_event_migration_rejects_wrong_legacy_unique_index_without_dropping_it():
    """同名但定义错误的旧索引必须阻断迁移，不能被迁移误删。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute(
                "CREATE TABLE third_party_report_logs ("
                "id INT NOT NULL AUTO_INCREMENT, source VARCHAR(50) NOT NULL, "
                "adsid VARCHAR(500) NOT NULL, event VARCHAR(50) NOT NULL, "
                "conversion_id VARCHAR(255) NULL, PRIMARY KEY (id), "
                "KEY unique_source_adsid (event)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            cursor.execute(
                "INSERT INTO third_party_report_logs "
                "(source, adsid, event, conversion_id) "
                "VALUES ('synthetic-source', 'synthetic-adsid', 'Purchase', 'synthetic-conversion')"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261110_third_party_report_event_idempotency.sql",
                )
            assert migration_error.value.args[0] == 1146
            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            indexes = cursor.fetchall()
            index_names = {row[2] for row in indexes}
            assert "unique_source_adsid" in index_names
            assert "unique_event_key" in index_names
            legacy_rows = [row for row in indexes if row[2] == "unique_source_adsid"]
            assert len(legacy_rows) == 1
            assert legacy_rows[0][1] == 1
            assert legacy_rows[0][4] == "event"
            cursor.execute(
                "SELECT source, adsid, event, conversion_id "
                "FROM third_party_report_logs WHERE id = 1"
            )
            assert cursor.fetchone() == (
                "synthetic-source", "synthetic-adsid", "Purchase", "synthetic-conversion"
            )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()


def test_outbox_migration_rejects_wrong_same_name_due_index():
    """错误的同名 Outbox 索引必须阻断迁移，不能被静默视为已存在。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute(
                "CREATE TABLE third_party_report_logs ("
                "id INT NOT NULL AUTO_INCREMENT, amount DECIMAL(12,2) NULL, "
                "status VARCHAR(20) NOT NULL DEFAULT 'pending', report_start_time DATETIME NULL, "
                "PRIMARY KEY (id), KEY idx_third_party_outbox_due (status)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            with pytest.raises(pymysql.err.OperationalError) as migration_error:
                _run_sql_file(cursor, "sql/migrations/20261111_third_party_report_outbox.sql")
            assert migration_error.value.args[0] == 1061
            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            indexes = cursor.fetchall()
            assert [row[4] for row in indexes if row[2] == "idx_third_party_outbox_due"] == ["status"]
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'third_party_report_logs' "
                "AND COLUMN_NAME = 'next_retry_time'"
            )
            assert cursor.fetchone() == ("next_retry_time",)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()


def test_outbox_migration_rejects_prefix_same_name_due_index():
    """列名正确但带前缀的同名 Outbox 索引不能冒充完整索引。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute(
                "CREATE TABLE third_party_report_logs ("
                "id INT NOT NULL AUTO_INCREMENT, outbox_enqueued TINYINT(1) NOT NULL DEFAULT 0, "
                "status VARCHAR(20) NOT NULL DEFAULT 'pending', next_retry_time DATETIME NULL, "
                "report_start_time DATETIME NULL, PRIMARY KEY (id), "
                "KEY idx_third_party_outbox_due "
                "(outbox_enqueued, status(5), next_retry_time, report_start_time, id)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            with pytest.raises(pymysql.err.OperationalError) as migration_error:
                _run_sql_file(cursor, "sql/migrations/20261111_third_party_report_outbox.sql")
            assert migration_error.value.args[0] == 1061
            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            indexes = [
                row for row in cursor.fetchall()
                if row[2] == "idx_third_party_outbox_due"
            ]
            assert len(indexes) == 5
            status_index = next(row for row in indexes if row[4] == "status")
            assert status_index[7] == 5
            assert all(row[1] == 1 for row in indexes)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()


def test_pii_migration_rejects_wrong_same_name_retention_index():
    """错误的同名 PII 扫描索引必须阻断迁移，避免跳过必要索引。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute(
                "CREATE TABLE third_party_report_logs ("
                "id INT NOT NULL AUTO_INCREMENT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "completed_at DATETIME NULL, PRIMARY KEY (id), "
                "KEY idx_third_party_pii_retention (created_at)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            cursor.execute(
                "CREATE TABLE postback_forward_logs ("
                "id INT NOT NULL AUTO_INCREMENT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "completed_at DATETIME NULL, PRIMARY KEY (id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            with pytest.raises(pymysql.err.OperationalError) as migration_error:
                _run_sql_file(cursor, "sql/migrations/20261112_third_party_report_pii_retention.sql")
            assert migration_error.value.args[0] == 1061
            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            indexes = cursor.fetchall()
            assert [row[4] for row in indexes if row[2] == "idx_third_party_pii_retention"] == ["created_at"]
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'third_party_report_logs' "
                "AND COLUMN_NAME = 'pii_scrubbed_at'"
            )
            assert cursor.fetchone() == ("pii_scrubbed_at",)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()

def test_pii_migration_rejects_unique_same_name_forward_retention_index():
    """下游转发日志的同名唯一索引不能冒充普通保留扫描索引。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute(
                "CREATE TABLE third_party_report_logs ("
                "id INT NOT NULL AUTO_INCREMENT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "completed_at DATETIME NULL, PRIMARY KEY (id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            cursor.execute(
                "CREATE TABLE postback_forward_logs ("
                "id INT NOT NULL AUTO_INCREMENT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "completed_at DATETIME NULL, pii_scrubbed_at DATETIME NULL, "
                "PRIMARY KEY (id), UNIQUE KEY idx_forward_log_pii_retention "
                "(pii_scrubbed_at, created_at, id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            with pytest.raises(pymysql.err.OperationalError) as migration_error:
                _run_sql_file(cursor, "sql/migrations/20261112_third_party_report_pii_retention.sql")
            assert migration_error.value.args[0] == 1061
            cursor.execute("SHOW INDEX FROM postback_forward_logs")
            rows = [row for row in cursor.fetchall() if row[2] == "idx_forward_log_pii_retention"]
            assert len(rows) == 3
            assert all(row[1] == 0 for row in rows)
            assert [row[4] for row in sorted(rows, key=lambda row: row[3])] == [
                "pii_scrubbed_at", "created_at", "id"
            ]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()



def test_short_click_batch_migration_rejects_wrong_same_name_table():
    """短链接点击账本的错误同名表必须 fail-closed，且原表数据/结构不被覆盖。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS short_link_click_sync_batches")
            cursor.execute(
                "CREATE TABLE short_link_click_sync_batches ("
                "batch_id VARCHAR(64) NOT NULL PRIMARY KEY, "
                "short_code VARCHAR(20) NOT NULL"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
            cursor.execute(
                "INSERT INTO short_link_click_sync_batches (batch_id, short_code) "
                "VALUES ('keep-this-row', 'keep-code')"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261110_short_link_click_sync_idempotency.sql",
                )
            assert migration_error.value.args[0] == 1146
            cursor.execute(
                "SELECT batch_id, short_code FROM short_link_click_sync_batches"
            )
            assert cursor.fetchall() == (("keep-this-row", "keep-code"),)
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'short_link_click_sync_batches'"
            )
            assert cursor.fetchone()[0] == 2
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS short_link_click_sync_batches")
        connection.close()


def test_mysql_migrations_create_idempotency_schema_and_backfill_event_keys():
    baseline_schema = Path("sql/platform.sql").read_text(encoding="utf-8")
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            # 点击刷盘账本迁移可重复执行，不丢失已存在的数据。
            _run_sql_file(
                cursor,
                "sql/migrations/20261110_short_link_click_sync_idempotency.sql",
            )
            cursor.execute(
                "INSERT INTO short_link_click_sync_batches "
                "(batch_id, short_code, click_count) VALUES (%s, %s, %s)",
                ("ci-migration-batch", "ci-code", 3),
            )
            _run_sql_file(
                cursor,
                "sql/migrations/20261110_short_link_click_sync_idempotency.sql",
            )
            cursor.execute(
                "SELECT short_code, click_count FROM short_link_click_sync_batches "
                "WHERE batch_id = %s",
                ("ci-migration-batch",),
            )
            assert cursor.fetchone() == ("ci-code", 3)

            # 构造 main 旧版第三方日志结构及历史记录，验证真实 SQL 回填。
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute(
                """
                CREATE TABLE third_party_report_logs (
                    id INT NOT NULL AUTO_INCREMENT,
                    source VARCHAR(50) NOT NULL,
                    adsid VARCHAR(500) NOT NULL,
                    event VARCHAR(50) NOT NULL,
                    conversion_id VARCHAR(255) NULL,
                    amount DECIMAL(12, 2) NULL,
                    email VARCHAR(255) NULL,
                    ip VARCHAR(50) NULL,
                    phone VARCHAR(50) NULL,
                    ua TEXT NULL,
                    report_params TEXT NULL,
                    response_body TEXT NULL,
                    log_id VARCHAR(100) NULL,
                    error_message TEXT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    report_start_time DATETIME NULL,
                    completed_at DATETIME NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY unique_source_adsid (source, adsid)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_0900_ai_ci
                """
            )
            historical = ("短链", "广告|标识", "ViewContent", "转化:一")
            historical_case_variant = (
                "short-link", "case-variant-ad", "viewcontent", "case-sensitive-conversion"
            )
            cursor.executemany(
                "INSERT INTO third_party_report_logs "
                "(source, adsid, event, conversion_id) VALUES (%s, %s, %s, %s)",
                [historical, historical_case_variant],
            )

            # 构造历史下游转发日志，验证 PII 迁移同时覆盖该表且不改写历史内容。
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute(
                """
                CREATE TABLE postback_forward_logs (
                    id INT NOT NULL AUTO_INCREMENT,
                    conversion_id INT NOT NULL,
                    product_id INT NULL,
                    publisher_id INT NULL,
                    downstream_url VARCHAR(500) NOT NULL,
                    request_method VARCHAR(10) NOT NULL,
                    request_data TEXT NULL,
                    request_params TEXT NULL,
                    response_status INT NULL,
                    response_body TEXT NULL,
                    success BOOLEAN NOT NULL DEFAULT 0,
                    error_message TEXT NULL,
                    retry_count INT NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME NULL,
                    PRIMARY KEY (id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_0900_ai_ci
                """
            )
            cursor.execute(
                "INSERT INTO postback_forward_logs "
                "(conversion_id, downstream_url, request_method, request_params, "
                "response_body, created_at, completed_at) "
                "VALUES (1, %s, 'GET', %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (
                    "https://downstream.invalid/cb?email=alice%40example.invalid",
                    '{"email":"alice@example.invalid","ip":"203.0.113.8"}',
                    '{"echo":"alice@example.invalid"}',
                ),
            )

            # 模拟迁移在首个 ADD COLUMN 成功后中断：字段已存在但尚未回填。
            cursor.execute(
                "ALTER TABLE third_party_report_logs "
                "ADD COLUMN event_key VARCHAR(64) NULL COMMENT 'CI interrupted migration' AFTER event"
            )
            _run_sql_file(
                cursor,
                "sql/migrations/20261110_third_party_report_event_idempotency.sql",
            )
            # 完整重复执行必须保持安全且不改写已回填的事件身份。
            _run_sql_file(
                cursor,
                "sql/migrations/20261110_third_party_report_event_idempotency.sql",
            )

            cursor.execute(
                "SELECT event_key FROM third_party_report_logs WHERE id = 1"
            )
            assert cursor.fetchone()[0] == _event_key(*historical)
            cursor.execute(
                "SELECT event_key FROM third_party_report_logs WHERE id = 2"
            )
            # MySQL 默认 *_ci 排序规则不应让 SQL 将小写 viewcontent 当作 ViewContent；
            # 必须与 Python 的大小写敏感事件身份算法一致。
            assert cursor.fetchone()[0] == _event_key(*historical_case_variant)

            # 新索引允许同一 source/adsid 的不同事件分别入账。
            source, adsid = "short_link", "same-ad-id"
            rows = [
                (source, adsid, "ViewContent", None),
                (source, adsid, "Purchase", "conversion-001"),
            ]
            for row in rows:
                cursor.execute(
                    "INSERT INTO third_party_report_logs "
                    "(source, adsid, event, conversion_id, event_key) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (*row, _event_key(*row)),
                )

            assert _event_key(*rows[0]) != _event_key(*rows[1])
            with pytest.raises(pymysql.err.IntegrityError):
                cursor.execute(
                    "INSERT INTO third_party_report_logs "
                    "(source, adsid, event, conversion_id, event_key) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (*rows[1], _event_key(*rows[1])),
                )

            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            index_names = {row[2] for row in cursor.fetchall()}
            assert "unique_event_key" in index_names
            assert "unique_source_adsid" not in index_names
            event_key_column = _column_metadata(cursor, "third_party_report_logs", "event_key")
            assert event_key_column[1].lower() == "varchar(64)"
            assert event_key_column[2] == "NO"
            assert _index_columns(cursor, "third_party_report_logs", "unique_event_key") == ["event_key"]

            # 模拟 Outbox 迁移在第一个字段已添加后中断；续跑应补齐其它字段和索引。
            cursor.execute(
                "ALTER TABLE third_party_report_logs "
                "ADD COLUMN outbox_enqueued TINYINT(1) NOT NULL DEFAULT 0"
            )
            _run_sql_file(
                cursor,
                "sql/migrations/20261111_third_party_report_outbox.sql",
            )
            # 重复执行不应因重复字段/索引而失败。
            _run_sql_file(
                cursor,
                "sql/migrations/20261111_third_party_report_outbox.sql",
            )
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'third_party_report_logs'"
            )
            outbox_columns = {row[0] for row in cursor.fetchall()}
            assert {
                "outbox_enqueued",
                "short_link_id",
                "cloak_name",
                "short_code",
                "click_time",
                "next_retry_time",
            }.issubset(outbox_columns)
            assert "facebook_access_token" not in outbox_columns

            cursor.execute(
                "SELECT outbox_enqueued FROM third_party_report_logs WHERE id = 1"
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "UPDATE third_party_report_logs SET outbox_enqueued = 1, short_link_id = 7, "
                "cloak_name = 'ci-cloak', short_code = 'ci-short', "
                "next_retry_time = CURRENT_TIMESTAMP WHERE id = 1"
            )
            cursor.execute(
                "SELECT outbox_enqueued, short_link_id, cloak_name, short_code "
                "FROM third_party_report_logs WHERE id = 1"
            )
            assert cursor.fetchone() == (1, 7, "ci-cloak", "ci-short")

            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            outbox_index_names = {row[2] for row in cursor.fetchall()}
            assert "idx_third_party_outbox_due" in outbox_index_names
            for column_name, expected_type in (
                ("outbox_enqueued", "tinyint(1)"),
                ("short_link_id", "int"),
                ("cloak_name", "varchar(100)"),
                ("short_code", "varchar(100)"),
                ("click_time", "datetime"),
                ("next_retry_time", "datetime"),
            ):
                metadata = _column_metadata(cursor, "third_party_report_logs", column_name)
                assert metadata is not None, column_name
                assert metadata[1].lower() == expected_type, column_name
            outbox_flag = _column_metadata(cursor, "third_party_report_logs", "outbox_enqueued")
            assert outbox_flag[2] == "NO"
            assert str(outbox_flag[4]) == "0"
            assert _index_columns(cursor, "third_party_report_logs", "idx_third_party_outbox_due") == [
                "outbox_enqueued", "status", "next_retry_time", "report_start_time", "id"
            ]

            # PII 清理迁移仅增加标记/索引，不在迁移时删除历史数据。
            cursor.execute(
                "UPDATE third_party_report_logs SET email = %s, ip = %s, phone = %s, "
                "ua = %s, report_params = %s, response_body = %s WHERE id = 1",
                (
                    "alice@example.invalid", "203.0.113.8", "4155550123",
                    "ci-private-agent", '{"email":"alice@example.invalid"}',
                    '{"echo":"alice@example.invalid"}',
                ),
            )
            # 模拟 PII 迁移在第一张表的清理标记列创建后中断。
            cursor.execute(
                "ALTER TABLE third_party_report_logs "
                "ADD COLUMN pii_scrubbed_at DATETIME NULL"
            )
            _run_sql_file(
                cursor,
                "sql/migrations/20261112_third_party_report_pii_retention.sql",
            )
            # 包括两个表的字段/索引在内，整份脚本可安全重跑。
            _run_sql_file(
                cursor,
                "sql/migrations/20261112_third_party_report_pii_retention.sql",
            )
            cursor.execute(
                "SELECT email, ip, phone, ua, report_params, response_body, "
                "pii_scrubbed_at, event_key FROM third_party_report_logs WHERE id = 1"
            )
            pii_row = cursor.fetchone()
            assert pii_row[:6] == (
                "alice@example.invalid", "203.0.113.8", "4155550123",
                "ci-private-agent", '{"email":"alice@example.invalid"}',
                '{"echo":"alice@example.invalid"}',
            )
            assert pii_row[6] is None
            assert pii_row[7] == _event_key(*historical)

            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            pii_index_names = {row[2] for row in cursor.fetchall()}
            assert "idx_third_party_pii_retention" in pii_index_names

            cursor.execute(
                "SELECT downstream_url, request_params, response_body, pii_scrubbed_at "
                "FROM postback_forward_logs WHERE id = 1"
            )
            forward_row = cursor.fetchone()
            assert forward_row == (
                "https://downstream.invalid/cb?email=alice%40example.invalid",
                '{"email":"alice@example.invalid","ip":"203.0.113.8"}',
                '{"echo":"alice@example.invalid"}',
                None,
            )
            cursor.execute("SHOW INDEX FROM postback_forward_logs")
            forward_index_names = {row[2] for row in cursor.fetchall()}
            assert "idx_forward_log_pii_retention" in forward_index_names
            for table_name in ("third_party_report_logs", "postback_forward_logs"):
                pii_metadata = _column_metadata(cursor, table_name, "pii_scrubbed_at")
                assert pii_metadata is not None
                assert pii_metadata[1].lower() == "datetime"
                assert pii_metadata[2] == "YES"
            assert _index_columns(cursor, "third_party_report_logs", "idx_third_party_pii_retention") == [
                "pii_scrubbed_at", "created_at", "id"
            ]
            assert _index_columns(cursor, "postback_forward_logs", "idx_forward_log_pii_retention") == [
                "pii_scrubbed_at", "created_at", "id"
            ]

            for column in (
                "pii_scrubbed_at",
                "idx_third_party_pii_retention",
                "idx_forward_log_pii_retention",
                "outbox_enqueued",
                "short_link_id",
                "cloak_name",
                "short_code",
                "click_time",
                "next_retry_time",
                "idx_third_party_outbox_due",
            ):
                assert column in baseline_schema

            # 使用两个独立 MySQL 连接真实竞争同一 Outbox 行的租约。
            # 这验证 InnoDB 条件 UPDATE 的实际仲裁，而不是仅模拟 rowcount。
            cursor.execute(
                "INSERT INTO third_party_report_logs "
                "(source, adsid, event, event_key, conversion_id, amount, status, "
                "outbox_enqueued, next_retry_time, report_start_time) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 1, CURRENT_TIMESTAMP, NULL)",
                (
                    "postback", "ci-outbox-claim", "Purchase",
                    hashlib.sha256(b"ci-outbox-claim").hexdigest(),
                    "ci-outbox-conversion", "1.00", "pending",
                ),
            )
            cursor.execute(
                "SELECT id FROM third_party_report_logs WHERE adsid = %s",
                ("ci-outbox-claim",),
            )
            claim_row_id = cursor.fetchone()[0]

            barrier = threading.Barrier(2)

            def _claim_from_independent_connection():
                claim_connection = _connect()
                claim_connection.autocommit(False)
                try:
                    barrier.wait(timeout=5)
                    with claim_connection.cursor() as claim_cursor:
                        claim_cursor.execute(
                            "UPDATE third_party_report_logs "
                            "SET report_start_time = CURRENT_TIMESTAMP "
                            "WHERE id = %s AND outbox_enqueued = 1 "
                            "AND status IN ('pending', 'failed') "
                            "AND (report_start_time IS NULL OR "
                            "report_start_time < DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 300 SECOND)) "
                            "AND (next_retry_time IS NULL OR next_retry_time <= CURRENT_TIMESTAMP)",
                            (claim_row_id,),
                        )
                        affected = claim_cursor.rowcount
                    claim_connection.commit()
                    return affected
                finally:
                    claim_connection.close()

            with ThreadPoolExecutor(max_workers=2) as executor:
                claim_results = list(
                    executor.map(
                        lambda _: _claim_from_independent_connection(),
                        range(2),
                    )
                )
            assert sorted(claim_results) == [0, 1], (
                "同一 Outbox 行只能由一个独立 MySQL worker 取得发送租约"
            )
    finally:
        connection.close()



def test_cap_reservation_migration_is_idempotent_and_matches_mysql_schema():
    """在 CI 专用 MySQL 8.0.16+ 实际执行账本迁移，核对 CHECK、字段、索引和 utf8mb4。"""
    baseline_schema = Path("sql/platform.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS cap_reservations" in baseline_schema
    assert "redis_token_cleaned" in baseline_schema
    for check_name in (
        "chk_cap_reservation_key_sha256",
        "chk_cap_reservation_offer_positive",
        "chk_cap_reservation_publisher_positive",
        "chk_cap_reservation_attempts_nonnegative",
        "chk_cap_reservation_kind_date",
        "chk_cap_reservation_state",
    ):
        assert check_name in baseline_schema

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            migration = "sql/migrations/20261111_cap_reservation_ledger.sql"
            _run_sql_file(cursor, migration)
            # CREATE TABLE IF NOT EXISTS 必须允许重复部署，不得破坏既有账本数据。
            cursor.execute(
                "INSERT INTO cap_reservations "
                "(reservation_key, platform, conversion_id, event_name, offer_id, "
                "cap_kind, business_date, redis_counter_key, redis_token_key, state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "a" * 64, "ci", "conversion-1", "purchase", 77,
                    "daily", "2026-11-11", "counter:key",
                    "counter:key:reservation:" + "a" * 64, "PREPARED",
                ),
            )
            _run_sql_file(cursor, migration)

            cursor.execute(
                "SELECT reservation_key, state, redis_reserved, redis_token_cleaned "
                "FROM cap_reservations WHERE reservation_key = %s",
                ("a" * 64,),
            )
            assert cursor.fetchone() == ("a" * 64, "PREPARED", 0, 0)

            cursor.execute("SHOW CREATE TABLE cap_reservations")
            create_sql = cursor.fetchone()[1]
            assert "DEFAULT CHARSET=utf8mb4" in create_sql
            assert "COLLATE=utf8mb4_unicode_ci" in create_sql
            assert "redis_reserved" in create_sql
            assert "redis_token_cleaned" in create_sql

            cursor.execute("SHOW INDEX FROM cap_reservations")
            index_names = {row[2] for row in cursor.fetchall()}
            assert {
                "uq_cap_reservation_key",
                "idx_cap_reservation_state_updated",
                "idx_cap_reservation_lease",
                "idx_cap_reservation_event",
                "idx_cap_reservation_scope",
            }.issubset(index_names)

            cursor.execute(
                "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations' "
                "AND CONSTRAINT_TYPE = 'CHECK'"
            )
            check_names = {row[0] for row in cursor.fetchall()}
            assert {
                "chk_cap_reservation_key_sha256",
                "chk_cap_reservation_offer_positive",
                "chk_cap_reservation_publisher_positive",
                "chk_cap_reservation_attempts_nonnegative",
                "chk_cap_reservation_kind_date",
                "chk_cap_reservation_state",
            }.issubset(check_names)

            # 数据库必须真正拒绝非法账本语义，不能只依赖 Python Service 校验。
            with pytest.raises(pymysql.err.OperationalError) as check_error:
                cursor.execute(
                    "INSERT INTO cap_reservations "
                    "(reservation_key, platform, conversion_id, event_name, offer_id, "
                    "cap_kind, business_date, redis_counter_key, redis_token_key, state) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        "b" * 64, "ci", "conversion-invalid", "purchase", 77,
                        "daily", None, "counter:key", "counter:key:reservation:invalid",
                        "PREPARED",
                    ),
                )
            # MySQL CHECK 约束错误码 3819 在 PyMySQL 中映射为 OperationalError。
            assert check_error.value.args[0] == 3819

            cursor.execute(
                "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations'"
            )
            columns = {row[0]: (row[1].lower(), row[2]) for row in cursor.fetchall()}
            assert columns["id"] == ("int", "NO")
            assert columns["reservation_key"] == ("varchar(64)", "NO")
            assert columns["publisher_id"][1] == "YES"
            assert columns["business_date"][1] == "YES"
            assert columns["redis_reserved"] == ("tinyint(1)", "NO")
            assert columns["redis_token_cleaned"] == ("tinyint(1)", "NO")
    finally:
        connection.close()







def test_cap_reservation_migration_rejects_database_side_updated_at_trigger():
    """迁移表不能额外引入 ORM 模型未声明的数据库级 ON UPDATE 行为。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            _run_sql_file(cursor, "sql/migrations/20261111_cap_reservation_ledger.sql")
            cursor.execute(
                "ALTER TABLE cap_reservations MODIFY updated_at "
                "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP "
                "ON UPDATE CURRENT_TIMESTAMP"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261111_cap_reservation_ledger.sql",
                )
            assert migration_error.value.args[0] == 1146
            cursor.execute(
                "SELECT LOWER(EXTRA) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations' "
                "AND COLUMN_NAME = 'updated_at'"
            )
            assert "on update" in cursor.fetchone()[0]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
        connection.close()


def test_cap_reservation_migration_rejects_wrong_column_default():
    """关键状态列的默认值漂移必须阻断迁移，不能只核对字段类型与 NULL 属性。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            _run_sql_file(cursor, "sql/migrations/20261111_cap_reservation_ledger.sql")
            cursor.execute(
                "ALTER TABLE cap_reservations ALTER COLUMN attempts SET DEFAULT 5"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261111_cap_reservation_ledger.sql",
                )
            assert migration_error.value.args[0] == 1146
            cursor.execute(
                "SELECT COLUMN_DEFAULT FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations' "
                "AND COLUMN_NAME = 'attempts'"
            )
            assert cursor.fetchone()[0] == "5"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
        connection.close()


def test_cap_reservation_migration_rejects_non_unique_same_name_unique_index():
    """同名同列但唯一性错误的索引必须被拒绝，不能只比较索引名称与列顺序。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            _run_sql_file(cursor, "sql/migrations/20261111_cap_reservation_ledger.sql")
            cursor.execute("ALTER TABLE cap_reservations DROP INDEX uq_cap_reservation_key")
            cursor.execute(
                "ALTER TABLE cap_reservations ADD INDEX uq_cap_reservation_key (reservation_key)"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261111_cap_reservation_ledger.sql",
                )
            assert migration_error.value.args[0] == 1146
            cursor.execute(
                "SHOW INDEX FROM cap_reservations WHERE Key_name = %s",
                ("uq_cap_reservation_key",),
            )
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0][1] == 1  # NON_UNIQUE：原错误索引仍存在且未被迁移改写
            assert rows[0][4] == "reservation_key"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
        connection.close()


def test_cap_reservation_migration_rejects_wrong_same_name_table():
    """同名但结构错误的 Cap 账本表必须阻断迁移，不能被 IF NOT EXISTS 静默放过。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            cursor.execute(
                "CREATE TABLE cap_reservations ("
                "id INT NOT NULL AUTO_INCREMENT, reservation_key VARCHAR(64) NOT NULL, "
                "PRIMARY KEY (id), UNIQUE KEY uq_cap_reservation_key (reservation_key)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261111_cap_reservation_ledger.sql",
                )
            # MySQL 1146 为不存在表；PyMySQL 将其映射为 ProgrammingError。
            assert migration_error.value.args[0] == 1146
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations'"
            )
            assert {row[0] for row in cursor.fetchall()} == {"id", "reservation_key"}
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
        connection.close()


def test_mysql_outbox_commit_ack_loss_preserves_stable_event_identity():
    """在隔离 MySQL/InnoDB 上注入 COMMIT 响应丢失，验证两种提交结果都可安全恢复。

    此测试在 COMMIT 已由服务端执行后，故意让测试客户端抛出连接错误，
    模拟客户端未收到 COMMIT 响应；另验证事务实际回滚时，同一 event_key 可重试。
    不调用真实第三方接口，也不连接生产数据库。
    """
    table = "third_party_report_ack_loss_ci"
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            cursor.execute(
                f"CREATE TABLE {table} ("
                "id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
                "event_key CHAR(64) NOT NULL, "
                "status VARCHAR(20) NOT NULL, "
                "UNIQUE KEY uq_ack_loss_event_key (event_key)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )

        # 情形一：MySQL 已提交，但客户端没有收到 COMMIT ACK。
        committed_key = hashlib.sha256(b"ci-outbox-commit-ack-lost").hexdigest()
        connection.autocommit(False)
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {table} (event_key, status) VALUES (%s, %s)",
                (committed_key, "pending"),
            )
        connection.commit()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {table} SET status = %s WHERE event_key = %s",
                    ("success", committed_key),
                )
            connection.commit()  # InnoDB 服务端已确认事务提交。
            raise pymysql.err.OperationalError(
                2013, "simulated lost COMMIT acknowledgement after server commit"
            )
        except pymysql.err.OperationalError as exc:
            assert "simulated lost COMMIT acknowledgement" in str(exc)
        finally:
            connection.close()

        # 新连接核对真实持久化结果：成功状态已经提交，事件仍只有一条。
        verify = _connect()
        try:
            with verify.cursor() as cursor:
                cursor.execute(
                    f"SELECT status, COUNT(*) OVER () FROM {table} WHERE event_key = %s",
                    (committed_key,),
                )
                assert cursor.fetchone() == ("success", 1)
                with pytest.raises(pymysql.err.IntegrityError):
                    cursor.execute(
                        f"INSERT INTO {table} (event_key, status) VALUES (%s, %s)",
                        (committed_key, "pending"),
                    )
        finally:
            verify.close()

        # 情形二：连接故障发生在事务提交前，数据库回滚；同一 event_key 重试成功。
        rolled_back_key = hashlib.sha256(b"ci-outbox-commit-not-applied").hexdigest()
        retry_connection = _connect()
        retry_connection.autocommit(False)
        try:
            with retry_connection.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {table} (event_key, status) VALUES (%s, %s)",
                    (rolled_back_key, "pending"),
                )
            retry_connection.commit()
            with retry_connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {table} SET status = %s WHERE event_key = %s",
                    ("success", rolled_back_key),
                )
            retry_connection.rollback()
            raise pymysql.err.OperationalError(
                2013, "simulated connection loss before COMMIT was applied"
            )
        except pymysql.err.OperationalError as exc:
            assert "before COMMIT was applied" in str(exc)
        finally:
            retry_connection.close()

        retry_verify = _connect()
        try:
            retry_verify.autocommit(False)
            with retry_verify.cursor() as cursor:
                cursor.execute(
                    f"SELECT status FROM {table} WHERE event_key = %s",
                    (rolled_back_key,),
                )
                assert cursor.fetchone() == ("pending",)
                cursor.execute(
                    f"UPDATE {table} SET status = %s WHERE event_key = %s",
                    ("success", rolled_back_key),
                )
            retry_verify.commit()
            with retry_verify.cursor() as cursor:
                cursor.execute(
                    f"SELECT status, COUNT(*) OVER () FROM {table} WHERE event_key = %s",
                    (rolled_back_key,),
                )
                assert cursor.fetchone() == ("success", 1)
        finally:
            retry_verify.close()
    finally:
        cleanup = _connect()
        try:
            with cleanup.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
        finally:
            cleanup.close()


def _run_sql_file_with_ddl_interruption(cursor, relative_path: str, ddl_boundary: int) -> None:
    """在指定 DDL 执行完成后模拟进程退出；DDL 本身已提交，后续语句不再执行。"""
    sql = Path(relative_path).read_text(encoding="utf-8")
    # 故障注入必须使用与正常迁移相同的语句边界解析器。
    statements = split_mysql_statements(sql)
    ddl_count = 0
    for statement in statements:
        cursor.execute(statement)
        is_ddl_boundary = (
            statement.upper().startswith("ALTER TABLE ")
            or statement.upper() == "EXECUTE MIGRATION_STMT"
        )
        if is_ddl_boundary:
            ddl_count += 1
            if ddl_count == ddl_boundary:
                raise InterruptedError(
                    f"injected process exit after DDL boundary {ddl_boundary}"
                )
    raise AssertionError(
        f"DDL boundary {ddl_boundary} was not reached in {relative_path}; "
        f"observed {ddl_count} DDL boundaries"
    )


@pytest.mark.parametrize(
    ("migration_path", "ddl_boundary"),
    [
        ("sql/migrations/20261110_third_party_report_event_idempotency.sql", boundary)
        for boundary in range(1, 5)
    ] + [
        ("sql/migrations/20261111_third_party_report_outbox.sql", boundary)
        for boundary in range(1, 8)
    ] + [
        ("sql/migrations/20261112_third_party_report_pii_retention.sql", boundary)
        for boundary in range(1, 5)
    ],
)
def test_incremental_migrations_resume_after_each_ddl_boundary(migration_path, ddl_boundary):
    """逐个 DDL 边界模拟进程退出，随后重跑迁移并核验最终结构。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")

            if migration_path.endswith("event_idempotency.sql"):
                cursor.execute(
                    "CREATE TABLE third_party_report_logs ("
                    "id INT NOT NULL AUTO_INCREMENT, source VARCHAR(50) NOT NULL, "
                    "adsid VARCHAR(500) NOT NULL, event VARCHAR(50) NOT NULL, "
                    "conversion_id VARCHAR(255) NULL, PRIMARY KEY (id), "
                    "UNIQUE KEY unique_source_adsid (source, adsid)) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )
                cursor.execute(
                    "INSERT INTO third_party_report_logs "
                    "(source, adsid, event, conversion_id) VALUES ('ci', 'ad-1', 'Purchase', 'conv-1')"
                )
            elif migration_path.endswith("outbox.sql"):
                cursor.execute(
                    "CREATE TABLE third_party_report_logs ("
                    "id INT NOT NULL AUTO_INCREMENT, amount DECIMAL(12,2) NULL, "
                    "status VARCHAR(20) NOT NULL DEFAULT 'pending', "
                    "report_start_time DATETIME NULL, PRIMARY KEY (id)) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )
            else:
                cursor.execute(
                    "CREATE TABLE third_party_report_logs ("
                    "id INT NOT NULL AUTO_INCREMENT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "completed_at DATETIME NULL, PRIMARY KEY (id)) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )
                cursor.execute(
                    "CREATE TABLE postback_forward_logs ("
                    "id INT NOT NULL AUTO_INCREMENT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "completed_at DATETIME NULL, PRIMARY KEY (id)) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )

            with pytest.raises(InterruptedError, match="injected process exit"):
                _run_sql_file_with_ddl_interruption(cursor, migration_path, ddl_boundary)

            # 新连接模拟进程重启，避免依赖旧连接的 session 状态或预处理语句。
        connection.close()
        connection = _connect()
        with connection.cursor() as cursor:
            _run_sql_file(cursor, migration_path)
            _run_sql_file(cursor, migration_path)

            if migration_path.endswith("event_idempotency.sql"):
                metadata = _column_metadata(cursor, "third_party_report_logs", "event_key")
                assert metadata is not None and metadata[1].lower() == "varchar(64)"
                assert metadata[2] == "NO"
                assert _index_columns(cursor, "third_party_report_logs", "unique_event_key") == ["event_key"]
                cursor.execute("SHOW INDEX FROM third_party_report_logs")
                assert "unique_source_adsid" not in {row[2] for row in cursor.fetchall()}
                cursor.execute("SELECT COUNT(*) FROM third_party_report_logs WHERE event_key IS NULL")
                assert cursor.fetchone()[0] == 0
            elif migration_path.endswith("outbox.sql"):
                assert _index_columns(
                    cursor, "third_party_report_logs", "idx_third_party_outbox_due"
                ) == ["outbox_enqueued", "status", "next_retry_time", "report_start_time", "id"]
                for column in (
                    "outbox_enqueued", "short_link_id", "cloak_name",
                    "short_code", "click_time", "next_retry_time",
                ):
                    assert _column_metadata(cursor, "third_party_report_logs", column) is not None
            else:
                for table_name, index_name in (
                    ("third_party_report_logs", "idx_third_party_pii_retention"),
                    ("postback_forward_logs", "idx_forward_log_pii_retention"),
                ):
                    metadata = _column_metadata(cursor, table_name, "pii_scrubbed_at")
                    assert metadata is not None and metadata[1].lower() == "datetime"
                    assert metadata[2] == "YES"
                    assert _index_columns(cursor, table_name, index_name) == [
                        "pii_scrubbed_at", "created_at", "id"
                    ]
    finally:
        if connection.open:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
                cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()


def test_pii_migration_rejects_descending_same_name_retention_index():
    """同名降序索引不能冒充 PII 清理任务要求的升序扫描索引。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute(
                "CREATE TABLE third_party_report_logs ("
                "id INT NOT NULL AUTO_INCREMENT, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "completed_at DATETIME NULL, pii_scrubbed_at DATETIME NULL, "
                "PRIMARY KEY (id), "
                "KEY idx_third_party_pii_retention "
                "(pii_scrubbed_at DESC, created_at, id)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            cursor.execute(
                "CREATE TABLE postback_forward_logs ("
                "id INT NOT NULL AUTO_INCREMENT, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "completed_at DATETIME NULL, PRIMARY KEY (id)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )

            with pytest.raises(pymysql.err.OperationalError) as migration_error:
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261112_third_party_report_pii_retention.sql",
                )
            assert migration_error.value.args[0] == 1061

            cursor.execute("SHOW INDEX FROM third_party_report_logs")
            rows = [
                row for row in cursor.fetchall()
                if row[2] == "idx_third_party_pii_retention"
            ]
            assert len(rows) == 3
            assert all(row[1] == 1 for row in rows)
            assert [row[4] for row in sorted(rows, key=lambda row: row[3])] == [
                "pii_scrubbed_at", "created_at", "id"
            ]
            assert [row[5] for row in sorted(rows, key=lambda row: row[3])] == [
                "D", "A", "A"
            ]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()


@pytest.mark.parametrize(
    "wrong_table",
    ["third_party_report_logs", "postback_forward_logs"],
)
def test_pii_migration_rejects_automatic_default_on_retention_marker(wrong_table):
    """PII 清理标记不能带 CURRENT_TIMESTAMP 默认值，避免新记录被误标为已清理。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")

            third_party_marker = (
                "DATETIME NULL DEFAULT CURRENT_TIMESTAMP"
                if wrong_table == "third_party_report_logs"
                else "DATETIME NULL"
            )
            cursor.execute(
                "CREATE TABLE third_party_report_logs ("
                "id INT NOT NULL AUTO_INCREMENT, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "completed_at DATETIME NULL, "
                f"pii_scrubbed_at {third_party_marker}, "
                "PRIMARY KEY (id), "
                "KEY idx_third_party_pii_retention "
                "(pii_scrubbed_at, created_at, id)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )

            forward_marker = (
                "DATETIME NULL DEFAULT CURRENT_TIMESTAMP"
                if wrong_table == "postback_forward_logs"
                else "DATETIME NULL"
            )
            cursor.execute(
                "CREATE TABLE postback_forward_logs ("
                "id INT NOT NULL AUTO_INCREMENT, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "completed_at DATETIME NULL, "
                f"pii_scrubbed_at {forward_marker}, "
                "PRIMARY KEY (id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )

            with pytest.raises(pymysql.err.OperationalError) as migration_error:
                _run_sql_file(
                    cursor,
                    "sql/migrations/20261112_third_party_report_pii_retention.sql",
                )
            assert migration_error.value.args[0] == 1060

            cursor.execute(
                "SELECT COLUMN_DEFAULT, EXTRA FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
                "AND COLUMN_NAME = 'pii_scrubbed_at'",
                (wrong_table,),
            )
            assert cursor.fetchone() == ("CURRENT_TIMESTAMP", "DEFAULT_GENERATED")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS postback_forward_logs")
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()


def test_report_identity_scope_migration_keeps_all_legacy_rows_unresolved_and_is_rerunnable():
    """真实隔离 MySQL 验证新身份列、旧行默认 unresolved 与 migration 幂等。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
            cursor.execute(
                """
                CREATE TABLE third_party_report_logs (
                    id INT NOT NULL AUTO_INCREMENT,
                    event_key VARCHAR(64) NOT NULL,
                    outbox_enqueued TINYINT(1) NOT NULL DEFAULT 0,
                    status VARCHAR(20) NOT NULL,
                    next_retry_time DATETIME NULL,
                    report_start_time DATETIME NULL,
                    PRIMARY KEY (id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.executemany(
                "INSERT INTO third_party_report_logs "
                "(event_key, outbox_enqueued, status) VALUES (%s, %s, %s)",
                [
                    ("legacy-direct-event-key", 0, "success"),
                    ("legacy-outbox-event-key", 1, "pending"),
                ],
            )

            migration = "sql/migrations/20261113_third_party_report_identity_scope.sql"
            _run_sql_file(cursor, migration)
            _run_sql_file(cursor, migration)

            cursor.execute(
                "SELECT identity_scope, platform, destination_pixel_id "
                "FROM third_party_report_logs ORDER BY id"
            )
            rows = list(cursor.fetchall())
            assert rows == [
                ("legacy_unresolved", None, None),
                ("legacy_unresolved", None, None),
            ]

            assert _column_metadata(cursor, "third_party_report_logs", "platform")[1] == "varchar(100)"
            assert _column_metadata(cursor, "third_party_report_logs", "identity_scope")[1] == "varchar(32)"
            assert _column_metadata(cursor, "third_party_report_logs", "destination_pixel_id")[1] == "varchar(100)"
            assert _index_columns(
                cursor,
                "third_party_report_logs",
                "idx_third_party_scope_due",
            ) == [
                "identity_scope",
                "platform",
                "outbox_enqueued",
                "status",
                "next_retry_time",
                "report_start_time",
                "id",
            ]
            cursor.execute(
                "SELECT COUNT(*) FROM third_party_report_logs "
                "WHERE identity_scope <> 'legacy_unresolved' "
                "OR platform IS NOT NULL OR destination_pixel_id IS NOT NULL"
            )
            assert cursor.fetchone()[0] == 0
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_logs")
        connection.close()


def test_report_identity_lock_migration_creates_permanent_collision_checked_lock_table():
    """隔离 MySQL 验证身份锁表 DDL 可重跑且锁键为唯一主键。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_identity_locks")
            migration = "sql/migrations/20261113_third_party_report_identity_scope_locks.sql"
            _run_sql_file(cursor, migration)
            _run_sql_file(cursor, migration)

            cursor.execute("SHOW COLUMNS FROM third_party_report_identity_locks")
            columns = {row[0]: row[1].lower() for row in cursor.fetchall()}
            assert columns["identity_key"] == "char(64)"
            assert columns["identity_fingerprint"] == "binary(64)"
            assert columns["created_at"] == "datetime"

            cursor.execute("SHOW INDEX FROM third_party_report_identity_locks")
            primary = [
                row[4]
                for row in cursor.fetchall()
                if row[2] == "PRIMARY"
            ]
            assert primary == ["identity_key"]

            identity_key = "a" * 64
            identity_value = "4:meta10:click-1238:Purchase7:conv-01".encode("utf-8")
            fingerprint = hashlib.sha512(identity_value).digest()
            cursor.execute(
                "INSERT INTO third_party_report_identity_locks "
                "(identity_key, identity_fingerprint) VALUES (%s, %s)",
                (identity_key, fingerprint),
            )
            cursor.execute(
                "SELECT identity_fingerprint FROM third_party_report_identity_locks "
                "WHERE identity_key = %s",
                (identity_key,),
            )
            assert cursor.fetchone()[0] == fingerprint

            # 同名但物理结构错误的表不能被 IF NOT EXISTS 静默接受。
            cursor.execute("DROP TABLE third_party_report_identity_locks")
            cursor.execute(
                "CREATE TABLE third_party_report_identity_locks ("
                "identity_key CHAR(64) NOT NULL PRIMARY KEY"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(cursor, migration)
            assert migration_error.value.args[0] == 1146
            cursor.execute("SHOW COLUMNS FROM third_party_report_identity_locks")
            assert [row[0] for row in cursor.fetchall()] == ["identity_key"]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS third_party_report_identity_locks")
        connection.close()

def test_cap_reservation_schema_guard_accepts_innodb_single_id_primary_key():
    """Cap 账本物理结构正确时，独立版本化后置核验必须通过。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            _run_sql_file(cursor, "sql/migrations/20261111_cap_reservation_ledger.sql")
            _run_sql_file(cursor, "sql/migrations/20261113_cap_reservation_schema_guard.sql")
            cursor.execute(
                "SELECT ENGINE FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations'"
            )
            assert cursor.fetchone()[0] == "InnoDB"
            cursor.execute(
                "SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations' "
                "AND INDEX_NAME = 'PRIMARY'"
            )
            assert cursor.fetchone()[0] == "id"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
        connection.close()


def test_cap_reservation_schema_guard_rejects_myisam_table():
    """同名表即使使用 id 主键，只要不是 InnoDB 就必须失败关闭。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            # 使用最小 MyISAM 表，避免 MyISAM 的 1000-byte 索引上限干扰引擎校验本身。
            cursor.execute(
                "CREATE TABLE cap_reservations (id INT NOT NULL, PRIMARY KEY (id)) "
                "ENGINE=MyISAM DEFAULT CHARSET=utf8mb4"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(cursor, "sql/migrations/20261113_cap_reservation_schema_guard.sql")
            assert migration_error.value.args[0] == 1146
            cursor.execute(
                "SELECT ENGINE FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations'"
            )
            assert cursor.fetchone()[0] == "MyISAM"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
        connection.close()


def test_cap_reservation_schema_guard_rejects_composite_primary_key():
    """主键唯一但列定义错误（id, offer_id）时不能通过物理结构核验。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            _run_sql_file(cursor, "sql/migrations/20261111_cap_reservation_ledger.sql")
            cursor.execute(
                "ALTER TABLE cap_reservations DROP PRIMARY KEY, "
                "ADD PRIMARY KEY (id, offer_id)"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(cursor, "sql/migrations/20261113_cap_reservation_schema_guard.sql")
            assert migration_error.value.args[0] == 1146
            cursor.execute(
                "SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cap_reservations' "
                "AND INDEX_NAME = 'PRIMARY'"
            )
            assert cursor.fetchone()[0] == "id,offer_id"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
        connection.close()

def test_cap_reservation_key_hex_migration_enforces_lowercase_sha256():
    """MySQL 必须拒绝非十六进制和大写 key，同时接受真实 SHA-256。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            _run_sql_file(cursor, "sql/migrations/20261111_cap_reservation_ledger.sql")
            _run_sql_file(cursor, "sql/migrations/20261113_cap_reservation_schema_guard.sql")
            _run_sql_file(cursor, "sql/migrations/20261113_cap_reservation_key_hex.sql")
            # 已有同名且定义正确的约束应通过后置核验，迁移可安全重复校验。
            _run_sql_file(cursor, "sql/migrations/20261113_cap_reservation_key_hex.sql")

            common = {
                "platform": "ci",
                "conversion_id": "synthetic-conversion",
                "event_name": "purchase",
                "offer_id": 77,
                "publisher_id": None,
                "cap_kind": "total",
                "business_date": None,
                "redis_counter_key": "counter:key",
                "redis_token_key": "counter:key:reservation",
                "redis_reserved": 0,
                "redis_token_cleaned": 0,
                "state": "PREPARED",
                "attempts": 0,
            }
            insert_sql = (
                "INSERT INTO cap_reservations "
                "(reservation_key, platform, conversion_id, event_name, offer_id, publisher_id, "
                "cap_kind, business_date, redis_counter_key, redis_token_key, redis_reserved, "
                "redis_token_cleaned, state, attempts) "
                "VALUES (%(reservation_key)s, %(platform)s, %(conversion_id)s, %(event_name)s, "
                "%(offer_id)s, %(publisher_id)s, %(cap_kind)s, %(business_date)s, "
                "%(redis_counter_key)s, %(redis_token_key)s, %(redis_reserved)s, "
                "%(redis_token_cleaned)s, %(state)s, %(attempts)s)"
            )
            valid_key = hashlib.sha256(b"synthetic-cap-reservation").hexdigest()
            cursor.execute(insert_sql, {**common, "reservation_key": valid_key})

            for invalid_key in ("g" * 64, "A" * 64, "a" * 63 + "G"):
                # MySQL 8.0 对 CHECK 约束违规返回 ER_CHECK_CONSTRAINT_VIOLATED (3819)，
                # PyMySQL 将该服务端错误映射为 OperationalError，而不是 IntegrityError。
                with pytest.raises(pymysql.err.OperationalError) as constraint_error:
                    cursor.execute(insert_sql, {**common, "reservation_key": invalid_key})
                assert constraint_error.value.args[0] == 3819
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
        connection.close()


def test_cap_reservation_key_hex_migration_rejects_wrong_named_constraint():
    """同名 CHECK 若定义不正确，迁移必须失败关闭而非跳过。"""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
            _run_sql_file(cursor, "sql/migrations/20261111_cap_reservation_ledger.sql")
            cursor.execute(
                "ALTER TABLE cap_reservations ADD CONSTRAINT chk_cap_reservation_key_hex "
                "CHECK (LENGTH(reservation_key) = 64)"
            )
            with pytest.raises(pymysql.err.ProgrammingError) as migration_error:
                _run_sql_file(cursor, "sql/migrations/20261113_cap_reservation_key_hex.sql")
            assert migration_error.value.args[0] == 1146
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cap_reservations")
        connection.close()
