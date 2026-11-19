"""真实 MySQL schema drift 检查；仅允许 GitHub Actions loopback 临时实例。"""
from __future__ import annotations

import ipaddress
import os
import secrets

import pytest
import pymysql
from sqlalchemy import (
    Column,
    DateTime,
    FetchedValue,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    text,
    URL,
    create_engine,
    event,
)

from app.bootstrap.lifespan import _schema_metadata_drift


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
    raise RuntimeError("拒绝运行 MySQL schema drift 测试：必须使用 GitHub Actions loopback 临时 MySQL")

pytestmark = pytest.mark.skipif(
    not _SAFE_MYSQL_CI,
    reason="仅在 GitHub Actions loopback 临时 MySQL 中运行",
)


def test_mysql_schema_drift_detects_and_accepts_index_fk_and_collation_changes():
    database = f"platform_ci_drift_{secrets.token_hex(5)}"
    root = pymysql.connect(
        host=HOST,
        port=PORT,
        user=ROOT_USER,
        password=ROOT_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )
    engine = None
    try:
        with root.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
            cursor.execute(
                f"CREATE TABLE `{database}`.drift_parent ("
                "id INT NOT NULL PRIMARY KEY"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
            )
            cursor.execute(
                f"CREATE TABLE `{database}`.drift_child ("
                "id INT NOT NULL PRIMARY KEY, "
                "parent_id INT NOT NULL, "
                "label VARCHAR(20) NOT NULL, "
                "CONSTRAINT ck_drift_child_label_nonempty "
                "CHECK (label <> '' OR 1=1) NOT ENFORCED"
                ") ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci"
            )

        metadata = MetaData()
        Table(
            "drift_parent",
            metadata,
            Column("id", Integer, primary_key=True),
        )
        child = Table(
            "drift_child",
            metadata,
            Column("id", Integer, primary_key=True),
            Column(
                "parent_id",
                Integer,
                ForeignKey("drift_parent.id", ondelete="CASCADE", name="fk_drift_child_parent"),
                nullable=False,
            ),
            Column("label", String(20), nullable=False),
            CheckConstraint("label <> ''", name="ck_drift_child_label_nonempty"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_0900_ai_ci",
        )
        Index("ix_drift_child_label", child.c.label)
        Index("ix_drift_child_parent_id", child.c.parent_id)

        url = URL.create(
            "mysql+pymysql",
            username=ROOT_USER,
            password=ROOT_PASSWORD,
            host=HOST,
            port=PORT,
            database=database,
            query={"charset": "utf8mb4"},
        )
        engine = create_engine(url, pool_pre_ping=True)
        observed_queries = []
        def record_metadata_queries(_conn, _cursor, statement, _parameters, _context, _executemany):
            normalized = " ".join(statement.casefold().split())
            if "information_schema.columns" in normalized or "select database()" in normalized:
                observed_queries.append(normalized)

        event.listen(engine, "before_cursor_execute", record_metadata_queries)
        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)
        # 两张表只触发一次 schema 解析和一次批量 COLUMNS 查询，避免逐表 N+1。
        assert sum("select database()" in query for query in observed_queries) == 1
        assert sum("information_schema.columns" in query for query in observed_queries) == 1
        assert "drift_child" in drift["index_mismatches"]
        assert "drift_child" in drift["foreign_key_mismatches"]
        check_drift = drift["check_constraint_mismatches"]["drift_child"]
        assert check_drift["expressions"]["expected"] == {
            "ck_drift_child_label_nonempty": "label <> ''"
        }
        actual_check = check_drift["expressions"]["actual"][
            "ck_drift_child_label_nonempty"
        ]
        # MySQL Inspector 会规范化引号字符集、括号和空格；只验证危险表达式未被误判为一致。
        assert "or" in actual_check.casefold()
        assert "1 = 1" in actual_check.casefold()
        assert check_drift["unenforced"] == ["ck_drift_child_label_nonempty"]
        assert drift["table_option_mismatches"]["drift_child"] == {
            "mysql_charset": {"expected": "utf8mb4", "actual": "latin1"},
            "mysql_collate": {
                "expected": "utf8mb4_0900_ai_ci",
                "actual": "latin1_swedish_ci",
            },
        }

        with root.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE `{database}`.drift_child "
                "CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci, "
                "ADD INDEX ix_drift_child_label (label), "
                "ADD INDEX ix_drift_child_parent_id (parent_id), "
                "ADD CONSTRAINT fk_drift_child_parent "
                f"FOREIGN KEY (parent_id) REFERENCES `{database}`.drift_parent (id) ON DELETE CASCADE, "
                "DROP CHECK ck_drift_child_label_nonempty, "
                "ADD CONSTRAINT ck_drift_child_label_nonempty CHECK (label <> '') ENFORCED"
            )
        with engine.connect() as connection:
            corrected = _schema_metadata_drift(connection, metadata)
        assert corrected == {
            "missing_tables": [],
            "missing_columns": {},
            "column_type_mismatches": {},
            "nullable_mismatches": {},
            "column_attribute_mismatches": {},
            "column_default_mismatches": {},
            "column_default_unverifiable": {},
            "primary_key_mismatches": {},
            "index_mismatches": {},
            "unique_constraint_mismatches": {},
            "foreign_key_mismatches": {},
            "check_constraint_mismatches": {},
            "table_option_mismatches": {},
        }
    finally:
        if engine is not None:
            engine.dispose()
        with root.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        root.close()


def test_mysql_schema_drift_scopes_batched_column_metadata_by_schema():
    """不同 schema 的同名表必须使用各自的列属性，不能交叉污染。"""
    auto_database = f"platform_ci_auto_{secrets.token_hex(4)}"
    plain_database = f"platform_ci_plain_{secrets.token_hex(4)}"
    root = pymysql.connect(
        host=HOST,
        port=PORT,
        user=ROOT_USER,
        password=ROOT_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )
    engine = None
    try:
        with root.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{auto_database}` CHARACTER SET utf8mb4")
            cursor.execute(f"CREATE DATABASE `{plain_database}` CHARACTER SET utf8mb4")
            cursor.execute(
                f"CREATE TABLE `{auto_database}`.same_name "
                "(id INT NOT NULL AUTO_INCREMENT PRIMARY KEY) ENGINE=InnoDB"
            )
            cursor.execute(
                f"CREATE TABLE `{plain_database}`.same_name "
                "(id INT NOT NULL PRIMARY KEY) ENGINE=InnoDB"
            )

        metadata = MetaData()
        Table(
            "same_name",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            schema=auto_database,
        )
        Table(
            "same_name",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=False),
            schema=plain_database,
        )
        url = URL.create(
            "mysql+pymysql",
            username=ROOT_USER,
            password=ROOT_PASSWORD,
            host=HOST,
            port=PORT,
            database=auto_database,
            query={"charset": "utf8mb4"},
        )
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)
        assert drift["column_attribute_mismatches"] == {}
    finally:
        if engine is not None:
            engine.dispose()
        with root.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{auto_database}`")
            cursor.execute(f"DROP DATABASE IF EXISTS `{plain_database}`")
        root.close()


def test_mysql_schema_drift_detects_missing_auto_increment_attribute():
    """AUTO_INCREMENT 是 MySQL 列属性，必须与 ORM 单列整数主键定义一致。"""
    database = f"platform_ci_drift_{secrets.token_hex(5)}"
    root = pymysql.connect(
        host=HOST,
        port=PORT,
        user=ROOT_USER,
        password=ROOT_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )
    engine = None
    try:
        with root.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
            cursor.execute(
                f"CREATE TABLE `{database}`.drift_auto_increment ("
                "id INT NOT NULL PRIMARY KEY"
                ") ENGINE=InnoDB"
            )
            cursor.execute(
                f"CREATE TABLE `{database}`.drift_fk_parent ("
                "id INT NOT NULL AUTO_INCREMENT PRIMARY KEY"
                ") ENGINE=InnoDB"
            )
            cursor.execute(
                f"CREATE TABLE `{database}`.drift_fk_child ("
                "id INT NOT NULL PRIMARY KEY, "
                "CONSTRAINT fk_drift_fk_child_parent FOREIGN KEY (id) "
                f"REFERENCES `{database}`.drift_fk_parent (id)"
                ") ENGINE=InnoDB"
            )

        metadata = MetaData()
        Table(
            "drift_auto_increment",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
        )
        Table(
            "drift_fk_parent",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
        )
        Table(
            "drift_fk_child",
            metadata,
            Column(
                "id",
                Integer,
                ForeignKey("drift_fk_parent.id"),
                primary_key=True,
            ),
        )
        url = URL.create(
            "mysql+pymysql",
            username=ROOT_USER,
            password=ROOT_PASSWORD,
            host=HOST,
            port=PORT,
            database=database,
            query={"charset": "utf8mb4"},
        )
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)
        assert drift["column_attribute_mismatches"] == {
            "drift_auto_increment": {
                "id": {
                    "autoincrement": {"expected": True, "actual": False}
                }
            }
        }

        with root.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE `{database}`.drift_auto_increment "
                "MODIFY id INT NOT NULL AUTO_INCREMENT"
            )
        with engine.connect() as connection:
            corrected = _schema_metadata_drift(connection, metadata)
        assert corrected["column_attribute_mismatches"] == {}
    finally:
        if engine is not None:
            engine.dispose()
        with root.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        root.close()


def test_mysql_schema_drift_checks_explicit_server_defaults_only():
    """核验数据库 DEFAULT；不把 Python default 误认为数据库 DDL。"""
    database = f"platform_ci_defaults_{secrets.token_hex(5)}"
    root = pymysql.connect(
        host=HOST,
        port=PORT,
        user=ROOT_USER,
        password=ROOT_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )
    engine = None
    try:
        with root.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
            cursor.execute(
                f"CREATE TABLE `{database}`.default_probe ("
                "id INT NOT NULL PRIMARY KEY, "
                "count_value INT NOT NULL DEFAULT 0, "
                "label VARCHAR(32) NOT NULL DEFAULT 'legacy', "
                "created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3), "
                "python_only INT NOT NULL, "
                "fetched_only INT NOT NULL"
                ") ENGINE=InnoDB"
            )

        metadata = MetaData()
        Table(
            "default_probe",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("count_value", Integer, nullable=False, server_default="0"),
            Column("label", String(32), nullable=False, server_default="legacy"),
            Column(
                "created_at",
                DateTime(3),
                nullable=False,
                server_default=text("CURRENT_TIMESTAMP(3)"),
            ),
            # Python 端默认值不生成数据库 DEFAULT，不应触发 drift。
            Column("python_only", Integer, nullable=False, default=7),
            Column("fetched_only", Integer, nullable=False, server_default=FetchedValue()),
        )
        url = URL.create(
            "mysql+pymysql",
            username=ROOT_USER,
            password=ROOT_PASSWORD,
            host=HOST,
            port=PORT,
            database=database,
            query={"charset": "utf8mb4"},
        )
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            aligned = _schema_metadata_drift(connection, metadata)
        assert aligned["column_default_mismatches"] == {}
        assert aligned["column_default_unverifiable"] == {}

        with root.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE `{database}`.default_probe "
                "ALTER COLUMN count_value SET DEFAULT 9, "
                "ALTER COLUMN label SET DEFAULT 'changed'"
            )
            # 移除时间表达式默认值，验证 MySQL 元数据能检测到默认值缺失。
            cursor.execute(
                f"ALTER TABLE `{database}`.default_probe "
                "ALTER COLUMN created_at DROP DEFAULT"
            )
        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)
        assert drift["column_default_mismatches"] == {
            "default_probe": {
                "count_value": {"expected": "0", "actual": "9"},
                "label": {"expected": "legacy", "actual": "changed"},
                "created_at": {
                    "expected": "current_timestamp(3)",
                    "actual": null,
                },
            }
        }
        assert drift["column_default_unverifiable"] == {}

        with root.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE `{database}`.default_probe "
                "ALTER COLUMN count_value SET DEFAULT 0, "
                "ALTER COLUMN label SET DEFAULT 'legacy'"
            )
            cursor.execute(
                f"ALTER TABLE `{database}`.default_probe "
                "MODIFY COLUMN created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)"
            )
        with engine.connect() as connection:
            corrected = _schema_metadata_drift(connection, metadata)
        assert corrected["column_default_mismatches"] == {}
    finally:
        if engine is not None:
            engine.dispose()
        with root.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        root.close()
