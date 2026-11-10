"""Postback 重试队列并发领取回归测试。"""
from datetime import datetime

from sqlalchemy.dialects import mysql

from app.scheduler_module.tasks.forward_tasks import (
    FORWARD_TASK_LEASE_SECONDS,
    _due_forward_task_query,
)


def test_due_forward_task_query_uses_skip_locked():
    query = _due_forward_task_query(datetime(2026, 11, 10, 12, 0, 0))
    sql = str(query.compile(dialect=mysql.dialect())).upper()

    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "NEXT_RETRY_TIME" in sql
    assert "ORDER BY" in sql
    assert "LIMIT" in sql


def test_forward_task_lease_is_longer_than_http_connect_timeout():
    # HTTP connect timeout 当前为 5 秒；租约须明显长于单次正常转发时间。
    from app.core.postback.forwarding.http_client import HttpClient

    assert FORWARD_TASK_LEASE_SECONDS >= HttpClient.CONNECT_TIMEOUT * 10
