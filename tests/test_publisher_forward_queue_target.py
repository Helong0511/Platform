"""Publisher retry tasks must not masquerade as product tasks after FK SET NULL."""
from types import SimpleNamespace

import pytest

from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.processor import PostbackProcessor


class _Scalars:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalars(self):
        return _Scalars(self.value)


class _FakeDB:
    def __init__(self, publisher=None, execute_results=None):
        self.publisher = publisher
        self.execute_results = list(execute_results or [])
        self.statements = []
        self.added = []

    async def execute(self, statement):
        self.statements.append(statement)
        if self.execute_results:
            return _Result(self.execute_results.pop(0))
        return _Result(self.publisher)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_initial_publisher_queue_does_not_store_product_target():
    publisher = SimpleNamespace(
        id=44,
        is_active=True,
        postback_url="https://publisher.example/callback",
        postback_method="GET",
    )
    db = _FakeDB(publisher=publisher)
    conversion = SimpleNamespace(id=100, product_id=88)
    click_association = {"publisher_id": 44}

    queued = await PostbackProcessor._enqueue_downstream_forward_tasks(
        db=db,
        conversion=conversion,
        click_association=click_association,
        forward_publisher=True,
        forward_product=False,
    )

    assert queued == 1
    task = db.added[0]
    assert task.publisher_id == 44
    assert task.product_id is None


@pytest.mark.asyncio
async def test_publisher_retry_queue_does_not_store_product_target():
    # 第一次查询模拟 SELECT ... FOR UPDATE 命中转化主记录；
    # 第二次去重查询模拟队列中尚无该渠道任务。
    db = _FakeDB(execute_results=[100, None])
    conversion = SimpleNamespace(id=100, product_id=88)

    await PostbackForwarder._enqueue_publisher_forward_retry(
        db=db,
        conversion=conversion,
        publisher_id=44,
        downstream_url="https://publisher.example/callback",
        method="GET",
        params={"cid": "synthetic-click"},
        json_data=None,
    )

    assert len(db.added) == 1
    # 去重查询必须是 MySQL 当前读，不能读取等待行锁前的旧一致性快照。
    from sqlalchemy.dialects import mysql

    dedupe_sql = str(db.statements[1].compile(dialect=mysql.dialect())).upper()
    assert "FOR UPDATE" in dedupe_sql
    task = db.added[0]
    assert task.publisher_id == 44
    assert task.product_id is None
