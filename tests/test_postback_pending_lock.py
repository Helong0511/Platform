"""Postback 待确认记录锁查询及真实 MySQL InnoDB 并发验收。"""
from __future__ import annotations

import os
import threading
import time
import uuid

import pymysql
import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable
from sqlalchemy.orm import declarative_base

from app.core.postback.pending_lock import build_pending_for_update_statement
from app.models.models import PendingPostbackConversion


def test_pending_lock_can_read_any_status_without_dropping_row_lock():
    statement = build_pending_for_update_statement(
        PendingPostbackConversion,
        123,
        status=None,
    )
    sql = str(
        statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "pending_postback_conversions.id = 123" in sql
    assert "pending_postback_conversions.status =" not in sql
    assert sql.rstrip().endswith("FOR UPDATE")


def test_pending_lock_defaults_to_pending_status():
    statement = build_pending_for_update_statement(
        PendingPostbackConversion,
        123,
    )
    sql = str(
        statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "pending_postback_conversions.id = 123" in sql
    assert "pending_postback_conversions.status = 'pending'" in sql
    assert sql.rstrip().endswith("FOR UPDATE")


# 只允许连接 GitHub Actions 创建的 loopback MySQL platform_ci，
# 每次测试使用独立数据库；本地未显式授权时自动跳过。
_MYSQL_HOST = os.getenv("MYSQL_INTEGRATION_HOST")
_MYSQL_DATABASE = os.getenv("MYSQL_INTEGRATION_DATABASE", "platform_ci")
_MYSQL_ENABLED = (
    os.getenv("UNIT_TEST") == "1"
    and os.getenv("GITHUB_ACTIONS") == "true"
    and os.getenv("MYSQL_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _MYSQL_HOST in {"127.0.0.1", "localhost", "::1"}
    and _MYSQL_DATABASE == "platform_ci"
)
if os.getenv("GITHUB_ACTIONS") == "true" and not _MYSQL_ENABLED:
    raise RuntimeError("拒绝运行 Postback 行锁集成测试：MySQL 目标未通过隔离校验")


@pytest.mark.skipif(
    not _MYSQL_ENABLED,
    reason="仅在隔离的 GitHub Actions MySQL 8.0 服务中运行",
)
def test_mysql_innodb_pending_lock_serializes_concurrent_approval_reads():
    database = f"ci_pending_lock_{uuid.uuid4().hex[:12]}"
    host = _MYSQL_HOST
    port = int(os.getenv("MYSQL_INTEGRATION_PORT", "3306"))
    user = os.getenv("MYSQL_INTEGRATION_USER", "root")
    password = os.getenv("MYSQL_INTEGRATION_PASSWORD", "")

    def connect(database_name: str):
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database_name,
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=5,
        )

    admin = connect(_MYSQL_DATABASE)
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        admin.close()

    metadata = MetaData()
    pending_table = Table(
        "pending_postback_conversions",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("status", String(20), nullable=False),
        mysql_engine="InnoDB",
    )
    Base = declarative_base()

    class PendingLockRow(Base):
        __table__ = pending_table

    create_table_sql = str(
        CreateTable(pending_table).compile(dialect=mysql.dialect())
    )
    lock_sql = str(
        build_pending_for_update_statement(
            PendingLockRow, 1, status=None
        ).compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    first = None
    worker = None
    worker_connection = None
    second_started = threading.Event()
    second_finished = threading.Event()
    second_status = []
    worker_errors = []

    try:
        first = connect(database)
        with first.cursor() as cursor:
            cursor.execute(create_table_sql)
            cursor.execute(
                "INSERT INTO pending_postback_conversions (status) VALUES ('pending')"
            )
            pending_id = cursor.lastrowid
            first.commit()

        # 将测试 SQL 中的固定 ID 替换为刚创建的记录 ID。
        lock_sql = lock_sql.replace("id = 1", f"id = {pending_id}")

        def second_transaction():
            nonlocal worker_connection
            try:
                worker_connection = connect(database)
                with worker_connection.cursor() as cursor:
                    second_started.set()
                    cursor.execute(lock_sql)
                    row = cursor.fetchone()
                    second_status.append(row[1])
                    worker_connection.rollback()
            except Exception as exc:
                worker_errors.append(type(exc).__name__)
            finally:
                if worker_connection is not None:
                    worker_connection.close()
                second_finished.set()

        with first.cursor() as cursor:
            cursor.execute(lock_sql)
            assert cursor.fetchone()[1] == "pending"

        worker = threading.Thread(target=second_transaction, daemon=True)
        worker.start()
        assert second_started.wait(5), "第二个事务未能启动"

        # 第二个事务执行同一条 SELECT ... FOR UPDATE，应等待第一个事务释放行锁。
        time.sleep(0.2)
        second_was_blocked = not second_finished.is_set()

        with first.cursor() as cursor:
            cursor.execute(
                "UPDATE pending_postback_conversions SET status='approved' WHERE id=%s",
                (pending_id,),
            )
        first.commit()

        worker.join(timeout=10)
        assert not worker.is_alive(), "第二个事务未在行锁释放后完成"
        assert second_was_blocked, "第二个事务没有等待第一个事务的 InnoDB 行锁"
        assert worker_errors == []
        assert second_status == ["approved"]
    finally:
        if first is not None:
            try:
                first.rollback()
            finally:
                first.close()
        if worker is not None and worker.is_alive():
            worker.join(timeout=5)
        cleanup = connect(_MYSQL_DATABASE)
        try:
            with cleanup.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            cleanup.commit()
        finally:
            cleanup.close()
