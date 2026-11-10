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
    def __init__(self, publisher=None):
        self.publisher = publisher
        self.added = []

    async def execute(self, statement):
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
    db = _FakeDB()
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
    task = db.added[0]
    assert task.publisher_id == 44
    assert task.product_id is None
