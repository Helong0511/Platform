"""队列 Worker 必须将持久化目标 ID 显式传给转发器。"""
from types import SimpleNamespace

import pytest

from app.core.postback.forwarder import PostbackForwarder
from app.scheduler_module.tasks import forward_tasks


class _Scalars:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _Result:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return _Scalars(self.value)


class _FakeDB:
    def __init__(self, conversion, successful_log):
        self.results = [conversion, successful_log]
        self.deleted = []
        self.committed = False

    async def execute(self, statement):
        return _Result(self.results.pop(0))

    async def delete(self, value):
        self.deleted.append(value)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_publisher_worker_passes_persisted_target_not_click_inference(monkeypatch):
    conversion = SimpleNamespace(id=10, click_id=None)
    task = SimpleNamespace(
        id=20,
        conversion_id=10,
        publisher_id=31,
        product_id=None,
        retry_count=0,
    )
    db = _FakeDB(conversion, SimpleNamespace(success=True))
    captured = {}

    async def forward(conversion_arg, db_arg, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(PostbackForwarder, "forward_to_publisher", forward)

    await forward_tasks.process_single_task(db, task)

    assert captured["target_publisher_id"] == 31
    assert "target_product_id" not in captured
    assert db.deleted == [task]
    assert db.committed is True


@pytest.mark.asyncio
async def test_product_worker_passes_persisted_target_not_conversion_current_value(monkeypatch):
    conversion = SimpleNamespace(id=10, click_id=None, product_id=99)
    task = SimpleNamespace(
        id=20,
        conversion_id=10,
        publisher_id=None,
        product_id=41,
        retry_count=0,
    )
    db = _FakeDB(conversion, SimpleNamespace(success=True))
    captured = {}

    async def forward(conversion_arg, db_arg, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(PostbackForwarder, "forward_to_product", forward)

    await forward_tasks.process_single_task(db, task)

    assert captured["target_product_id"] == 41
    assert "target_publisher_id" not in captured
    assert db.deleted == [task]
    assert db.committed is True


@pytest.mark.asyncio
async def test_worker_does_not_accept_stale_success_log_when_forwarder_skips(monkeypatch):
    conversion = SimpleNamespace(id=10, click_id=None)
    task = SimpleNamespace(
        id=20,
        conversion_id=10,
        publisher_id=31,
        product_id=None,
        retry_count=0,
    )
    stale_success = SimpleNamespace(id=100, success=True)
    db = _FakeDB(conversion, stale_success)
    db.results.append(stale_success)
    scheduled = []

    async def skipped_forward(*args, **kwargs):
        # 模拟目标停用/配置缺失时转发器提前返回，没有创建新日志。
        return None

    async def schedule(db_arg, task_arg):
        scheduled.append(task_arg)

    monkeypatch.setattr(PostbackForwarder, "forward_to_publisher", skipped_forward)
    monkeypatch.setattr(forward_tasks, "_schedule_or_drop_retry", schedule)

    await forward_tasks.process_single_task(db, task)

    assert scheduled == [task]
    assert db.deleted == []
    assert db.committed is False
