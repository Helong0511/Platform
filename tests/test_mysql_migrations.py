"""MySQL 8.0 隔离迁移集成测试。

只连接 CI 显式注入的临时 MySQL 服务；未配置时跳过。
禁止从应用生产配置读取数据库连接串。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
import pymysql


HOST = os.getenv("MYSQL_INTEGRATION_HOST")
pytestmark = pytest.mark.skipif(
    not HOST,
    reason="仅在显式配置的隔离 MySQL 集成环境中运行",
)


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
    # 当前迁移不包含存储过程；移除整行 SQL 注释后按语句执行，
    # 并对 SELECT 验证语句读取结果，确保连接可继续执行后续语句。
    statements = [
        statement.strip()
        for statement in "\n".join(
            line for line in sql.splitlines()
            if not line.lstrip().startswith("--")
        ).split(";")
        if statement.strip()
    ]
    for statement in statements:
        cursor.execute(statement)
        if cursor.description:
            cursor.fetchall()


def _event_key(source: str, adsid: str, event: str, conversion_id: str | None) -> str:
    parts = (source or "", adsid or "", event or "", conversion_id or "")
    identity = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def test_mysql_migrations_create_idempotency_schema_and_backfill_event_keys():
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
                    PRIMARY KEY (id),
                    UNIQUE KEY unique_source_adsid (source, adsid)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_0900_ai_ci
                """
            )
            historical = ("短链", "广告|标识", "ViewContent", "转化:一")
            cursor.execute(
                "INSERT INTO third_party_report_logs "
                "(source, adsid, event, conversion_id) VALUES (%s, %s, %s, %s)",
                historical,
            )

            _run_sql_file(
                cursor,
                "sql/migrations/20261110_third_party_report_event_idempotency.sql",
            )

            cursor.execute(
                "SELECT event_key FROM third_party_report_logs WHERE id = 1"
            )
            assert cursor.fetchone()[0] == _event_key(*historical)

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
