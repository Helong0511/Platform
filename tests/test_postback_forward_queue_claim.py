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
