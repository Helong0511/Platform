"""Scheduled Cap sync must make incomplete Redis snapshots visible to operators."""
from contextlib import asynccontextmanager

import pytest

from app.scheduler_module.tasks import cpl_tasks


@pytest.mark.asyncio
async def test_cap_sync_task_warns_when_any_counter_snapshot_is_skipped(monkeypatch, caplog):
    class FakeSynchronizer:
        def __init__(self, db):
            self.db = db

        async def sync_all_active_caps(self):
            return {"success": 2, "failed": 0, "skipped": 3}

    @asynccontextmanager
    async def fake_session():
        yield object()

    recorded = []
    monkeypatch.setattr(cpl_tasks, "AsyncSessionLocal", fake_session)
    monkeypatch.setattr(cpl_tasks, "CapSynchronizer", FakeSynchronizer)
    monkeypatch.setattr(
        cpl_tasks,
        "set_task_result",
        lambda task_name, message: recorded.append((task_name, message)),
    )

    with caplog.at_level("WARNING"):
        await cpl_tasks.cap_sync_task()

    assert recorded
    assert "skipped_missing_redis_key=3" in recorded[0][1]
    assert any("部分完成" in record.message for record in caplog.records)
