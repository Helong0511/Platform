"""调度锁与任务结果注册表的异常日志必须隐藏原始错误内容。"""
import logging

import pytest

import app.scheduler_module.lock as scheduler_lock
import app.scheduler_module.task_result_registry as result_registry


SECRET = "mysql://svc:db-password@internal.example/platform?token=private"


class _BrokenSession:
    info = {}

    async def rollback(self):
        return None

    async def close(self):
        return None

    async def execute(self, *_args, **_kwargs):
        raise RuntimeError(SECRET)


@pytest.mark.asyncio
async def test_acquire_task_lock_does_not_log_raw_database_exception(monkeypatch, caplog):
    db = _BrokenSession()
    monkeypatch.setattr(scheduler_lock, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(scheduler_lock, "_load_or_create_task_record", _raise_secret)

    with caplog.at_level(logging.ERROR):
        acquired, session = await scheduler_lock.acquire_task_lock("redaction-test")

    assert acquired is False
    assert session is None
    assert SECRET not in caplog.text
    assert "RuntimeError" in caplog.text


async def _raise_secret(*_args, **_kwargs):
    raise RuntimeError(SECRET)


@pytest.mark.asyncio
async def test_release_task_lock_does_not_log_raw_database_exception(caplog):
    db = _BrokenSession()

    with caplog.at_level(logging.ERROR):
        await scheduler_lock.release_task_lock(
            db,
            "redaction-test",
            success=False,
            result_message="safe summary",
            expected_run_count=1,
        )

    assert SECRET not in caplog.text
    assert "RuntimeError" in caplog.text


def test_task_result_getter_does_not_log_raw_exception(monkeypatch, caplog):
    def broken_getter(_task_name):
        raise RuntimeError(SECRET)

    monkeypatch.setitem(
        result_registry.TASK_RESULT_REGISTRY,
        "redaction-test",
        broken_getter,
    )

    with caplog.at_level(logging.DEBUG):
        result = result_registry.get_task_result("redaction-test")

    assert result is None
    assert SECRET not in caplog.text
    assert "RuntimeError" in caplog.text


def test_auto_register_does_not_log_import_exception_details(monkeypatch, caplog):
    monkeypatch.setattr(
        result_registry,
        "TASK_CONFIGS",
        {
            "redaction-test": {
                "task_name": "redaction-test",
                "result_getter_module": "app.tasks.redaction_test",
                "result_getter_function": "get_result",
            }
        },
    )

    def secret_import(*_args, **_kwargs):
        raise ImportError(SECRET)

    monkeypatch.setattr("builtins.__import__", secret_import)

    with caplog.at_level(logging.WARNING):
        result_registry.auto_register_task_results()

    assert SECRET not in caplog.text
    assert "ImportError" in caplog.text
}
