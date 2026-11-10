"""点击记录队列可靠性回归测试；全部使用 Fake Redis/DB，不连接外部服务。"""
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.core import clicks_queue
from app.scheduler_module.tasks import clicks_batch_processor as processor
from app.scheduler_module import scheduler


class _Result:
    def __init__(self, rows=None):
        self.rows = rows or []

    def all(self):
        return self.rows


class _DuplicateFallbackDB:
    def __init__(self):
        self.insert_attempts = 0
        self.rollback_calls = 0
        self.nested_calls = 0
        self.commit_calls = 0

    async def execute(self, statement):
        sql = str(statement).lstrip().upper()
        if sql.startswith("SELECT CLICKS.CLICK_ID"):
            return _Result([])
        if sql.startswith("INSERT INTO CLICKS"):
            self.insert_attempts += 1
            if self.insert_attempts in (1, 3):
                raise IntegrityError(
                    "INSERT INTO clicks",
                    {},
                    Exception("UNIQUE constraint failed: clicks.click_id"),
                )
            return _Result()
        raise AssertionError(f"unexpected SQL: {sql}")

    async def rollback(self):
        self.rollback_calls += 1

    async def commit(self):
        self.commit_calls += 1

    @asynccontextmanager
    async def begin_nested(self):
        self.nested_calls += 1
        yield


@pytest.mark.asyncio
async def test_bulk_duplicate_rolls_back_then_uses_savepoints_per_click():
    db = _DuplicateFallbackDB()
    clicks = [
        {"click_id": "click-a", "click_time": datetime(2026, 11, 10, 12, 0)},
        {"click_id": "click-b", "click_time": datetime(2026, 11, 10, 12, 1)},
    ]

    inserted, duplicates = await processor._batch_insert_clicks(db, clicks)

    assert (inserted, duplicates) == (1, 1)
    assert db.rollback_calls == 1
    assert db.nested_calls == 2
    # 事务由调用方统一提交，不能在逐条 fallback 中提前 commit。
    assert db.commit_calls == 0


@pytest.mark.asyncio
async def test_offer_validation_db_error_preserves_original_offer_id():
    class BrokenDB:
        async def execute(self, statement):
            raise OSError("isolated DB lookup failure")

    click = {"click_id": "click-offer", "offer_id": 321}
    with pytest.raises(OSError):
        await processor._validate_offer_ids(BrokenDB(), [click])
    assert click["offer_id"] == 321


@pytest.mark.asyncio
async def test_short_link_validation_db_error_preserves_original_foreign_key():
    class BrokenDB:
        async def execute(self, statement):
            raise OSError("isolated DB lookup failure")

    click = {"click_id": "click-short", "short_link_id": 654}
    with pytest.raises(OSError):
        await processor._validate_short_link_ids(BrokenDB(), [click])
    assert click["short_link_id"] == 654


def test_click_queue_task_uses_longer_lock_than_generic_tasks():
    assert scheduler._task_lock_timeout_seconds("点击记录队列批量处理") == 900
    assert scheduler._task_lock_timeout_seconds("普通统计任务") == scheduler.DEFAULT_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_enqueue_uses_single_atomic_capacity_and_rpush_script(monkeypatch):
    from app.core.tracking import click_persist

    class FakeRedis:
        def __init__(self, result):
            self.result = result
            self.calls = []

        async def eval(self, script, numkeys, key, payload, limit):
            self.calls.append((script, numkeys, key, payload, limit))
            return self.result

    monkeypatch.setattr(click_persist, "should_persist_clicks_to_db", lambda: True)
    redis = FakeRedis(-1)

    async def fake_redis():
        return redis

    monkeypatch.setattr(clicks_queue, "get_redis_client", fake_redis)
    accepted = await clicks_queue.enqueue_click({"click_id": "queue-cap"})

    assert accepted is False
    assert len(redis.calls) == 1
    script, numkeys, key, _payload, limit = redis.calls[0]
    assert numkeys == 1
    assert key == clicks_queue.CLICKS_QUEUE_KEY
    assert limit == clicks_queue.MAX_QUEUE_SIZE
    assert "LLEN" in script and "RPUSH" in script
    assert script.index("LLEN") < script.index("RPUSH")


@pytest.mark.asyncio
async def test_processing_recovery_uses_atomic_rpoplpush(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.items = ["raw-a", "raw-b"]
            self.calls = []

        async def rpoplpush(self, source, destination):
            self.calls.append((source, destination))
            return self.items.pop() if self.items else None

        async def rpop(self, key):
            raise AssertionError("non-atomic RPOP recovery is forbidden")

        async def lpush(self, *args):
            raise AssertionError("non-atomic LPUSH recovery is forbidden")

    redis = FakeRedis()

    async def fake_redis():
        return redis

    monkeypatch.setattr(clicks_queue, "get_redis_client", fake_redis)
    recovered = await clicks_queue.recover_processing_queue()

    assert recovered == 2
    assert redis.calls == [
        (clicks_queue.CLICKS_PROCESSING_KEY, clicks_queue.CLICKS_QUEUE_KEY),
        (clicks_queue.CLICKS_PROCESSING_KEY, clicks_queue.CLICKS_QUEUE_KEY),
        (clicks_queue.CLICKS_PROCESSING_KEY, clicks_queue.CLICKS_QUEUE_KEY),
    ]
