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

    # 整个下游 HTTP 请求有硬 deadline；租约额外预留 60 秒用于 DB/调度收尾。
    assert HttpClient.MAX_REDIRECTS == 10
    assert FORWARD_TASK_LEASE_SECONDS >= HttpClient.TOTAL_REQUEST_TIMEOUT_SECONDS + 60



def test_forward_queue_processor_is_registered_as_recurring_task():
    from app.scheduler_module.task_config import TASK_CONFIGS
    from app.scheduler_module.task_names import POSTBACK_FORWARD_QUEUE_TASK_NAME

    task = TASK_CONFIGS[POSTBACK_FORWARD_QUEUE_TASK_NAME]
    assert task["task_module"] == "app.scheduler_module.tasks.forward_tasks"
    assert task["task_function"] == "process_forward_queue"
    assert task["cron_expression"] == "*/1 * * * *"


def test_initial_forward_tasks_can_be_enqueued_in_conversion_transaction():
    import asyncio
    from types import SimpleNamespace

    from app.core.postback.processor import PostbackProcessor
    from app.models.models import Product, Publisher

    publisher = SimpleNamespace(
        id=31,
        is_active=True,
        postback_url="https://publisher.invalid/postback",
        postback_method="POST",
    )
    product = SimpleNamespace(
        id=41,
        is_active=True,
        downstream_postback_url="https://product.invalid/postback",
        downstream_postback_method="GET",
    )

    class FakeScalars:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

    class FakeResult:
        def __init__(self, value):
            self.value = value

        def scalars(self):
            return FakeScalars(self.value)

    class FakeDB:
        def __init__(self):
            self.added = []
            self.flushed = False

        async def execute(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            return FakeResult({Publisher: publisher, Product: product}[entity])

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            self.flushed = True

    db = FakeDB()
    conversion = SimpleNamespace(id=101, product_id=41)
    queued = asyncio.run(
        PostbackProcessor._enqueue_downstream_forward_tasks(
            db=db,
            conversion=conversion,
            click_association={"publisher_id": 31},
            forward_publisher=True,
            forward_product=True,
        )
    )

    assert queued == 2
    assert db.flushed is True
    assert len(db.added) == 2
    assert {item.publisher_id for item in db.added} == {31, None}
    assert {item.conversion_id for item in db.added} == {101}



async def test_admin_telegram_notification_does_not_hold_forward_queue_worker(monkeypatch):
    """Telegram 限流/重试属于旁路，不应占用转发任务租约。"""
    import asyncio

    from app.core.postback import forwarder
    from app.services.telegram_notification_service import TelegramNotificationService

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_notification(**kwargs):
        started.set()
        await release.wait()
        return True

    monkeypatch.setattr(
        TelegramNotificationService,
        "send_admin_notification",
        staticmethod(slow_notification),
    )

    forwarder._schedule_admin_notification(
        message="isolated test notification",
        telegram_chat_id="123456",
        notification_type="forward_success",
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    pending = [
        task for task in forwarder._notification_tasks
        if not task.done()
    ]
    assert len(pending) == 1

    release.set()
    await asyncio.wait_for(asyncio.gather(*pending), timeout=1)
    assert not forwarder._notification_tasks



async def test_postback_http_total_deadline_bounds_slow_streaming_response(monkeypatch):
    """HTTPX 单次 read timeout 不能限制慢速分块响应，必须执行总 deadline。"""
    import asyncio

    import httpx

    from app.core.postback.forwarding.http_client import HttpClient

    captured = {}

    class HangingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            await asyncio.Event().wait()

    def build_client(**kwargs):
        captured.update(kwargs)
        return HangingClient()

    monkeypatch.setattr(httpx, "AsyncClient", build_client)
    monkeypatch.setattr(HttpClient, "TOTAL_REQUEST_TIMEOUT_SECONDS", 0.01)

    result = await HttpClient.send_request(
        url="https://downstream.example.invalid/postback",
        method="GET",
    )

    assert result == (False, 0, "Timeout: Total request deadline exceeded")
    assert captured["max_redirects"] == HttpClient.MAX_REDIRECTS



async def test_retry_enqueue_serializes_on_conversion_row_lock():
    """并发入队前必须对 conversion 主记录加 MySQL 行锁。"""
    from sqlalchemy.dialects import mysql

    from app.core.postback.forwarder import _lock_conversion_for_queue_enqueue

    captured = {}

    class FakeScalars:
        def first(self):
            return 101

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    class FakeDB:
        async def execute(self, statement):
            compiled = statement.compile(dialect=mysql.dialect())
            captured["sql"] = str(compiled).upper()
            captured["params"] = compiled.params
            return FakeResult()

    assert await _lock_conversion_for_queue_enqueue(FakeDB(), 101) is True
    assert "FOR UPDATE" in captured["sql"]
    assert "POSTBACK_CONVERSIONS.ID" in captured["sql"]
    assert 101 in captured["params"].values()


async def test_retry_enqueue_skips_when_conversion_row_is_missing():
    from app.core.postback.forwarder import _lock_conversion_for_queue_enqueue

    class FakeScalars:
        def first(self):
            return None

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    class FakeDB:
        async def execute(self, statement):
            return FakeResult()

    assert await _lock_conversion_for_queue_enqueue(FakeDB(), 404) is False

def test_latest_forward_log_query_uses_primary_key_as_tiebreaker():
    from app.scheduler_module.tasks.forward_tasks import _latest_forward_log_query

    query = _latest_forward_log_query(101, publisher_id=31)
    sql = str(query.compile(dialect=mysql.dialect())).upper()

    assert "ORDER BY" in sql
    assert "POSTBACK_FORWARD_LOGS.CREATED_AT DESC" in sql
    assert "POSTBACK_FORWARD_LOGS.ID DESC" in sql
    assert "POSTBACK_FORWARD_LOGS.PUBLISHER_ID" in sql
    assert "LIMIT" in sql


def test_latest_product_forward_log_query_excludes_publisher_logs():
    from app.scheduler_module.tasks.forward_tasks import _latest_forward_log_query

    query = _latest_forward_log_query(101, product_id=41)
    sql = str(query.compile(dialect=mysql.dialect())).upper()

    assert "POSTBACK_FORWARD_LOGS.PRODUCT_ID" in sql
    assert "POSTBACK_FORWARD_LOGS.PUBLISHER_ID IS NULL" in sql
    assert "POSTBACK_FORWARD_LOGS.ID DESC" in sql


import logging
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_forward_queue_worker_does_not_log_raw_exception_details(
    monkeypatch, caplog
):
    from app.core.postback.forwarder import PostbackForwarder
    from app.scheduler_module.tasks import forward_tasks

    conversion = SimpleNamespace(id=31, click_id=None)
    task = SimpleNamespace(
        id=41,
        conversion_id=31,
        publisher_id=51,
        product_id=None,
        retry_count=0,
    )

    class ScalarResult:
        def first(self):
            return conversion

    class Result:
        def scalars(self):
            return ScalarResult()

    class FakeDB:
        async def execute(self, statement):
            return Result()

    async def fail_forward(*args, **kwargs):
        raise RuntimeError("buyer@example.invalid 203.0.113.10 secret-payload")

    async def no_retry(*args, **kwargs):
        return None

    monkeypatch.setattr(PostbackForwarder, "forward_to_publisher", fail_forward)
    monkeypatch.setattr(forward_tasks, "_schedule_or_drop_retry", no_retry)

    with caplog.at_level(logging.ERROR):
        await forward_tasks.process_single_task(FakeDB(), task)

    assert "buyer@example.invalid" not in caplog.text
    assert "203.0.113.10" not in caplog.text
    assert "secret-payload" not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_forward_queue_trigger_does_not_log_raw_exception_details(
    monkeypatch, caplog
):
    from app.scheduler_module.tasks import forward_tasks

    async def fail():
        raise RuntimeError("buyer@example.invalid 203.0.113.10 secret-payload")

    monkeypatch.setattr(forward_tasks, "process_forward_queue", fail)

    with caplog.at_level(logging.ERROR):
        await forward_tasks.trigger_forward_processing()

    assert "buyer@example.invalid" not in caplog.text
    assert "203.0.113.10" not in caplog.text
    assert "secret-payload" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_forward_log_request_summary_never_persists_parameter_values():
    import json

    from app.core.postback.forwarder import _safe_forward_log_request_summary

    summary = _safe_forward_log_request_summary(
        {
            "email": "buyer@example.invalid",
            "ip": "203.0.113.10",
            "click_id": "private-click-id",
            "payout": "12.50",
        }
    )

    assert json.loads(summary) == {"redacted": True, "field_count": 4}
    for sensitive_value in (
        "buyer@example.invalid",
        "203.0.113.10",
        "private-click-id",
        "12.50",
    ):
        assert sensitive_value not in summary
    assert _safe_forward_log_request_summary(None) is None
    assert _safe_forward_log_request_summary({}) is None
