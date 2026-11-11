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
import threading
from concurrent.futures import ThreadPoolExecutor


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
    # 必须与应用和 SQL migration 的身份规则一致：ViewContent 的 conversion_id
    # 可能由后续 Purchase 补写，仅用于关联，不属于 ViewContent 的幂等身份。
    identity_conversion_id = "" if event == "ViewContent" else (conversion_id or "")
    parts = (source or "", adsid or "", event or "", identity_conversion_id)
    identity = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


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
            cursor.execute(
                "INSERT INTO third_party_report_logs "
                "(source, adsid, event, conversion_id) VALUES (%s, %s, %s, %s)",
                historical,
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
