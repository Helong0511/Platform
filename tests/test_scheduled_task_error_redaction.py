"""定时任务管理服务不得向 API 或日志泄露数据库内部异常。"""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services.scheduled_task_service import ScheduledTaskService


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _BrokenDB:
    def __init__(self, task, error):
        self.task = task
        self.error = error
        self.rollback = AsyncMock()

    async def execute(self, _query):
        return _Result(self.task)

    async def flush(self):
        raise RuntimeError(self.error)


@pytest.mark.asyncio
async def test_update_scheduled_task_status_redacts_database_error(monkeypatch, caplog):
    secret = "mysql://svc:password@db.internal:3306/platform SELECT * FROM users"
    task = SimpleNamespace(
        task_name="daily-report",
        is_active=True,
        is_running=False,
        updated_at=None,
        function_path=None,
        cron_expression=None,
        description=None,
    )
    db = _BrokenDB(task, secret)
    service = ScheduledTaskService(db)
    user = SimpleNamespace(username="admin")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as caught:
            await service.update_scheduled_task_status(
                task_name="daily-report",
                is_active=False,
                current_user=user,
            )

    assert secret not in str(caught.value.detail)
    assert "更新定时任务状态失败，请稍后重试" in str(caught.value.detail)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_task_lock_redacts_database_error(caplog):
    secret = "postgresql://svc:password@db.internal:5432/platform"
    task = SimpleNamespace(
        task_name="daily-report",
        is_running=True,
        updated_at=None,
        last_error=None,
    )
    db = _BrokenDB(task, secret)
    service = ScheduledTaskService(db)
    user = SimpleNamespace(username="admin")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as caught:
            await service.release_task_lock(
                task_name="daily-report",
                current_user=user,
            )

    assert secret not in str(caught.value.detail)
    assert "释放任务锁失败，请稍后重试" in str(caught.value.detail)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    db.rollback.assert_awaited_once()
