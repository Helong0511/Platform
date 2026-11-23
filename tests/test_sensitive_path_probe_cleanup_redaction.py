"""敏感路径日志清理失败时不得把数据库异常原文写入任务结果或日志。"""
import logging
from unittest.mock import AsyncMock

import pytest

from app.scheduler_module.task_result_store import clear_task_result, get_task_result
from app.scheduler_module.tasks import cleanup_sensitive_path_probes as cleanup_module


class _BrokenDB:
    async def execute(self, _statement):
        raise RuntimeError("mysql://svc:secret@db.internal:3306/platform SELECT * FROM secrets")

    rollback = AsyncMock()
    close = AsyncMock()


@pytest.mark.asyncio
async def test_cleanup_failure_redacts_database_exception(monkeypatch, caplog):
    secret = "mysql://svc:secret@db.internal:3306/platform SELECT * FROM secrets"
    db = _BrokenDB()
    clear_task_result(cleanup_module.TASK_NAME)
    monkeypatch.setattr(cleanup_module, "AsyncSessionLocal", lambda: db)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError, match="mysql://"):
            await cleanup_module.cleanup_sensitive_path_probe_logs(retention_days=30)

    result = get_task_result(cleanup_module.TASK_NAME)
    assert result == "清理失败（RuntimeError）"
    assert secret not in result
    assert secret not in caplog.text
    db.rollback.assert_awaited_once()
    db.close.assert_awaited_once()
