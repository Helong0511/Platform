"""队列 Worker 必须绑定持久化目标，并且只能由当前租约持有者修改队列状态。"""
from types import SimpleNamespace

import pytest

from app.core.postback.forwarder import PostbackForwarder, _bind_publisher_target
from app.scheduler_module.tasks import forward_tasks


class _Scalars:
    def __init__(self, value): self.value = value
    def first(self): return self.value


class _Result:
    def __init__(self, value): self.value = value
    def scalars(self): return _Scalars(self.value)


class _FakeDB:
    def __init__(self, conversion, previous_log, latest_log=None):
        if latest_log is None:
            latest_log = SimpleNamespace(id=previous_log.id + 1, success=True)
        self.results = [conversion, previous_log, latest_log]
        self.deleted = []
        self.committed = False
    async def execute(self, statement): return _Result(self.results.pop(0))
    async def delete(self, value): self.deleted.append(value)
    async def commit(self): self.committed = True
    async def rollback(self): pass


def _install_owned_lease_stubs(monkeypatch, task):
    async def renew(db, task_id, token): return task_id == task.id and token == task.lease_token
    async def delete_owned(db, task_id, token):
        if task_id != task.id or token != task.lease_token: return False
        await db.delete(task)
        await db.commit()
        return True
    monkeypatch.setattr(forward_tasks, "_renew_forward_task_lease", renew)
    monkeypatch.setattr(forward_tasks, "_delete_owned_forward_task", delete_owned)


@pytest.mark.asyncio
async def test_publisher_worker_passes_persisted_target_not_click_inference(monkeypatch):
    conversion = SimpleNamespace(id=10, click_id=None)
    task = SimpleNamespace(id=20, conversion_id=10, publisher_id=31, product_id=None, retry_count=0, lease_token="a" * 32)
    db = _FakeDB(conversion, SimpleNamespace(id=100, success=False))
    _install_owned_lease_stubs(monkeypatch, task)
    captured = {}
    async def forward(conversion_arg, db_arg, **kwargs): captured.update(kwargs)
    monkeypatch.setattr(PostbackForwarder, "forward_to_publisher", forward)
    await forward_tasks.process_single_task(db, task)
    assert captured["target_publisher_id"] == 31
    assert "target_product_id" not in captured
    assert db.deleted == [task]
    assert db.committed is True


@pytest.mark.asyncio
async def test_product_worker_passes_persisted_target_not_conversion_current_value(monkeypatch):
    conversion = SimpleNamespace(id=10, click_id=None, product_id=99)
    task = SimpleNamespace(id=20, conversion_id=10, publisher_id=None, product_id=41, retry_count=0, lease_token="c" * 32)
    db = _FakeDB(conversion, SimpleNamespace(id=100, success=False))
    _install_owned_lease_stubs(monkeypatch, task)
    captured = {}
    async def forward(conversion_arg, db_arg, **kwargs): captured.update(kwargs)
    monkeypatch.setattr(PostbackForwarder, "forward_to_product", forward)
    await forward_tasks.process_single_task(db, task)
    assert captured["target_product_id"] == 41
    assert "target_publisher_id" not in captured
    assert db.deleted == [task]
    assert db.committed is True


@pytest.mark.asyncio
async def test_worker_does_not_accept_stale_success_log_when_forwarder_skips(monkeypatch):
    conversion = SimpleNamespace(id=10, click_id=None)
    task = SimpleNamespace(id=20, conversion_id=10, publisher_id=31, product_id=None, retry_count=0, lease_token="b" * 32)
    stale_success = SimpleNamespace(id=100, success=True)
    db = _FakeDB(conversion, stale_success, stale_success)
    _install_owned_lease_stubs(monkeypatch, task)
    scheduled = []
    async def skipped_forward(*args, **kwargs): return None
    async def schedule(db_arg, task_arg, lease_token): scheduled.append((task_arg, lease_token))
    monkeypatch.setattr(PostbackForwarder, "forward_to_publisher", skipped_forward)
    monkeypatch.setattr(forward_tasks, "_schedule_or_drop_retry", schedule)
    await forward_tasks.process_single_task(db, task)
    assert scheduled == [(task, task.lease_token)]
    assert db.deleted == []
    assert db.committed is False


def test_persisted_publisher_target_overrides_stale_click_association_identity():
    click_data = {"publisher_id": 12, "offer_id": 88, "click_id": "click-1"}
    bound = _bind_publisher_target(click_data, 31)
    assert bound["publisher_id"] == 31
    assert bound["offer_id"] == 88
    assert bound["click_id"] == "click-1"
    assert click_data["publisher_id"] == 12


def test_non_queue_publisher_binding_preserves_click_association_identity():
    click_data = {"publisher_id": 12, "click_id": "click-1"}
    bound = _bind_publisher_target(click_data, None)
    assert bound == click_data
    assert bound is not click_data


@pytest.mark.asyncio
async def test_expired_or_replaced_lease_cannot_renew_or_delete(monkeypatch):
    task = SimpleNamespace(id=77, lease_token="old-token")
    async def reject_renew(db, task_id, token): return False
    async def forbidden_forward(*args, **kwargs): raise AssertionError("stale worker must not send")
    monkeypatch.setattr(forward_tasks, "_renew_forward_task_lease", reject_renew)
    monkeypatch.setattr(PostbackForwarder, "forward_to_publisher", forbidden_forward)
    db = _FakeDB(SimpleNamespace(id=10, click_id=None), SimpleNamespace(id=1, success=False))
    await forward_tasks.process_single_task(db, task)
    assert db.deleted == []
