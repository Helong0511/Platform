"""验证同名定时任务并发时队列跟踪不会相互覆盖。"""
import asyncio

import pytest

from app.scheduler_module.task_queue import TaskQueue


@pytest.mark.asyncio
async def test_same_name_tasks_are_tracked_and_waited_independently():
    queue = TaskQueue(max_concurrent_tasks=2)
    both_started = asyncio.Event()
    release = asyncio.Event()
    started = 0

    async def task_body():
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await release.wait()

    await queue.submit("same-task", task_body)
    await queue.submit("same-task", task_body)

    await asyncio.wait_for(both_started.wait(), timeout=2)
    status = await queue.get_queue_status()
    assert status["current_running"] == 2
    assert status["running_tasks"] == ["same-task", "same-task"]

    release.set()
    await asyncio.wait_for(queue.wait_for_completion(), timeout=2)

    final_status = await queue.get_queue_status()
    assert final_status["current_running"] == 0
    assert final_status["running_tasks"] == []
    assert final_status["queue_length"] == 0
