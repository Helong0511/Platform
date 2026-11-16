"""队列 Worker 必须将持久化目标 ID 显式传给转发器。"""
from types import SimpleNamespace

import pytest

from app.core.postback.forwarder import PostbackForwarder, _bind_publisher_target
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
    def __init__(self, conversion, previous_log, latest_log=None):
        if latest_log is None:
            latest_log = SimpleNamespace(id=previous_log.id + 1, success=True)
        self.results = [conversion, previous_log, latest_log]
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
        lease_token='a' * 32,
    )
    db = _FakeDB(conversion, SimpleNamespace(id=100, success=False))
    captured = {}
    async def renew(db_arg, task_id, token):
        return token == task.lease_token
    async def delete_owned(db_arg, task_id, token):
        await db_arg.delete(task)
        await db_arg.commit()
        return True
    monkeypatch.setattr(forward_tasks, '_renew_forward_task_lease', renew)
    monkeypatch.setattr(forward_tasks, '_delete_owned_forward_task', delete_owned)

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
        lease_token='b' * 32,
    )
    stale_success = SimpleNamespace(id=100, success=True)
    db = _FakeDB(conversion, stale_success, stale_success)
    async def renew(db_arg, task_id, token):
        return token == task.lease_token
    monkeypatch.setattr(forward_tasks, '_renew_forward_task_lease', renew)
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



def test_persisted_publisher_target_overrides_stale_click_association_identity():
    click_data = {
        "publisher_id": 12,
        "offer_id": 88,
        "click_id": "click-1",
    }

    bound = _bind_publisher_target(click_data, 31)

    assert bound["publisher_id"] == 31
    assert bound["offer_id"] == 88
    assert bound["click_id"] == "click-1"
    # 不修改调用方持有的原始 Click 关联快照。
    assert click_data["publisher_id"] == 12


def test_non_queue_publisher_binding_preserves_click_association_identity():
    click_data = {"publisher_id": 12, "click_id": "click-1"}

    bound = _bind_publisher_target(click_data, None)

    assert bound == click_data
    assert bound is not click_data
