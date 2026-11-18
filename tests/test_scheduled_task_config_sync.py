"""定时任务配置同步的原子性、幂等性与失败语义测试。"""

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.models.system import ScheduledTask
from app.scheduler_module import task_init


def _config(name: str, function: str = "run") -> dict:
    return {
        "task_name": name,
        "task_module": "app.scheduler_module.tasks.test_tasks",
        "task_function": function,
        "cron_expression": "*/5 * * * *",
        "description": f"测试任务 {name}",
    }


@pytest.mark.asyncio
async def test_task_config_sync_is_atomic_and_idempotent(monkeypatch):
    """重复同步不重置管理员禁用状态或运行统计，同时更新配置字段。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(ScheduledTask.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(task_init, "AsyncSessionLocal", factory)
        monkeypatch.setattr(
            task_init,
            "TASK_CONFIGS",
            {"first": _config("测试任务一"), "second": _config("测试任务二")},
        )

        await task_init.init_scheduled_tasks_in_db()

        async with factory() as session:
            first = await session.scalar(
                select(ScheduledTask).where(ScheduledTask.task_name == "测试任务一")
            )
            assert first is not None
            first.is_active = False
            first.run_count = 17
            await session.commit()

        monkeypatch.setattr(
            task_init,
            "TASK_CONFIGS",
            {
                "first": _config("测试任务一", function="updated"),
                "second": _config("测试任务二"),
            },
        )
        await task_init.init_scheduled_tasks_in_db()

        async with factory() as session:
            rows = list((await session.scalars(select(ScheduledTask))).all())
            first = next(row for row in rows if row.task_name == "测试任务一")
            assert len(rows) == 2
            assert first.function_path.endswith(".updated")
            assert first.is_active is False
            assert first.run_count == 17
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_config_sync_rolls_back_entire_batch_on_commit_failure(monkeypatch):
    """批次提交失败必须回滚全部新任务，并向启动调用方传播失败。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    failure_raised = False

    def fail_first_commit(session):
        nonlocal failure_raised
        if not failure_raised:
            failure_raised = True
            raise RuntimeError("synthetic commit failure")

    try:
        async with engine.begin() as connection:
            await connection.run_sync(ScheduledTask.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(task_init, "AsyncSessionLocal", factory)
        monkeypatch.setattr(
            task_init,
            "TASK_CONFIGS",
            {"first": _config("原子任务一"), "second": _config("原子任务二")},
        )
        event.listen(Session, "before_commit", fail_first_commit)
        try:
            with pytest.raises(RuntimeError, match="synthetic commit failure"):
                await task_init.init_scheduled_tasks_in_db()
        finally:
            event.remove(Session, "before_commit", fail_first_commit)

        async with factory() as session:
            rows = list((await session.scalars(select(ScheduledTask))).all())
            assert rows == []
    finally:
        if event.contains(Session, "before_commit", fail_first_commit):
            event.remove(Session, "before_commit", fail_first_commit)
        await engine.dispose()


def test_task_sync_only_retries_duplicate_key_conflicts():
    """唯一键竞争可识别为可重试；其它数据库错误不能误判为并发。"""
    duplicate = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: scheduled_tasks.task_name"))
    other = IntegrityError("INSERT", {}, Exception("NOT NULL constraint failed: scheduled_tasks.task_name"))
    deadlock = OperationalError("SELECT", {}, Exception(1213, "Deadlock found"))
    timeout = OperationalError("SELECT", {}, Exception(1205, "Lock wait timeout exceeded"))

    assert task_init._is_retryable_task_sync_conflict(duplicate)
    assert task_init._is_retryable_task_sync_conflict(deadlock)
    assert task_init._is_retryable_task_sync_conflict(timeout)
    assert not task_init._is_retryable_task_sync_conflict(other)


def test_task_config_sync_rejects_duplicate_task_names(monkeypatch):
    """配置键不同但 task_name 相同也必须在写库前拒绝。"""
    monkeypatch.setattr(
        task_init,
        "TASK_CONFIGS",
        {"first": _config("重复任务"), "second": _config("重复任务")},
    )

    with pytest.raises(ValueError, match="重复 task_name"):
        # 配置校验在首次 await 数据库上下文之前执行。
        import asyncio
        asyncio.run(task_init.init_scheduled_tasks_in_db())
