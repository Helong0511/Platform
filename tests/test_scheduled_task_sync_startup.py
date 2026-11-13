"""启动阶段定时任务配置同步策略测试。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.bootstrap import lifespan as lifespan_module


@pytest.mark.asyncio
async def test_scheduler_worker_refuses_start_when_task_sync_fails(monkeypatch, caplog):
    """调度 Worker 不得在任务配置同步失败后使用旧配置启动。"""

    async def fail_sync():
        raise RuntimeError("synthetic database detail must not be logged")

    monkeypatch.setattr(lifespan_module, "init_scheduled_tasks_in_db", fail_sync)
    monkeypatch.setattr(
        lifespan_module,
        "settings",
        SimpleNamespace(should_run_scheduler=lambda: True),
    )

    with pytest.raises(RuntimeError, match="调度 Worker 拒绝启动") as error:
        await lifespan_module._sync_scheduled_tasks_for_worker(123)

    assert isinstance(error.value.__cause__, RuntimeError)
    assert "synthetic database detail" not in caplog.text
    assert "exception_type=RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_api_only_worker_can_degrade_when_task_sync_fails(monkeypatch, caplog):
    """不运行 APScheduler 的纯 API Worker 保持既有降级启动策略。"""

    async def fail_sync():
        raise RuntimeError("synthetic database detail must not be logged")

    monkeypatch.setattr(lifespan_module, "init_scheduled_tasks_in_db", fail_sync)
    monkeypatch.setattr(
        lifespan_module,
        "settings",
        SimpleNamespace(should_run_scheduler=lambda: False),
    )

    await lifespan_module._sync_scheduled_tasks_for_worker(456)

    assert "exception_type=RuntimeError" in caplog.text
    assert "synthetic database detail" not in caplog.text


@pytest.mark.asyncio
async def test_worker_logs_success_after_task_config_sync(monkeypatch):
    """同步成功时正常记录成功状态。"""

    async def successful_sync():
        return None

    info = Mock()
    monkeypatch.setattr(lifespan_module.logger, "info", info)
    monkeypatch.setattr(lifespan_module, "init_scheduled_tasks_in_db", successful_sync)
    monkeypatch.setattr(
        lifespan_module,
        "settings",
        SimpleNamespace(should_run_scheduler=lambda: True),
    )

    await lifespan_module._sync_scheduled_tasks_for_worker(789)

    info.assert_called_once_with(
        "[Worker PID:%s] 定时任务配置已同步到数据库", 789
    )



@pytest.mark.asyncio
async def test_scheduler_initialization_failure_prevents_worker_readiness(monkeypatch):
    """APScheduler 初始化失败时，调度 Worker 必须启动失败。"""
    from unittest.mock import AsyncMock

    init_scheduler = AsyncMock(side_effect=RuntimeError("synthetic scheduler detail"))
    start_scheduler = AsyncMock()
    error = Mock()
    monkeypatch.setattr(lifespan_module, "init_scheduled_tasks", init_scheduler)
    monkeypatch.setattr(lifespan_module, "start_scheduler", start_scheduler)
    monkeypatch.setattr(lifespan_module.logger, "error", error)

    with pytest.raises(RuntimeError, match="调度 Worker 拒绝就绪") as raised:
        await lifespan_module._start_scheduler_for_worker(321)

    assert isinstance(raised.value.__cause__, RuntimeError)
    init_scheduler.assert_awaited_once_with()
    start_scheduler.assert_not_awaited()
    assert "synthetic scheduler detail" not in str(error.call_args)


@pytest.mark.asyncio
async def test_scheduler_starts_only_after_successful_initialization(monkeypatch):
    """调度器初始化成功后才执行启动调用。"""
    from unittest.mock import AsyncMock

    init_scheduler = AsyncMock()
    start_scheduler = AsyncMock()
    monkeypatch.setattr(lifespan_module, "init_scheduled_tasks", init_scheduler)
    monkeypatch.setattr(lifespan_module, "start_scheduler", start_scheduler)

    await lifespan_module._start_scheduler_for_worker(654)

    init_scheduler.assert_awaited_once_with()
    start_scheduler.assert_awaited_once_with()
