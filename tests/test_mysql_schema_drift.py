"""真实 MySQL schema drift 检查；仅允许 GitHub Actions loopback 临时实例。"""
from __future__ import annotations

import ipaddress
import os
import secrets

import pytest
import pymysql
from sqlalchemy import (
    Column,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    URL,
    create_engine,
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
        with engine.connect() as connection:
            drift = _schema_metadata_drift(connection, metadata)
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

        metadata = MetaData()
        Table(
            "drift_auto_increment",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
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
