"""验证定时任务队列的容量背压、关闭状态与排空超时语义。"""
import asyncio

import pytest

from app.scheduler_module.task_queue import (
    QueueFullError,
    QueueShuttingDownError,
    TaskQueue,
)


@pytest.mark.asyncio
async def test_queue_rejects_new_waiting_task_when_capacity_is_full():
    queue = TaskQueue(max_concurrent_tasks=1, max_pending_tasks=1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_task():
        started.set()
        await release.wait()

    await queue.submit("running", blocked_task)
    await asyncio.wait_for(started.wait(), timeout=2)
    await queue.submit("queued", blocked_task)

    with pytest.raises(QueueFullError):
        await queue.submit("rejected", blocked_task)

    status = await queue.get_queue_status()
    assert status["current_running"] == 1
    assert status["queue_length"] == 1
    assert status["queued_tasks"] == ["queued"]

    release.set()
    await asyncio.wait_for(queue.wait_for_completion(timeout=2), timeout=3)


@pytest.mark.asyncio
async def test_queue_stops_accepting_without_discarding_accepted_tasks():
    queue = TaskQueue(max_concurrent_tasks=1, max_pending_tasks=2)
    started = asyncio.Event()
    release = asyncio.Event()
    completed = []

    async def blocked_task(name):
        if name == "first":
            started.set()
            await release.wait()
        completed.append(name)

    await queue.submit("first", blocked_task, name="first")
    await asyncio.wait_for(started.wait(), timeout=2)
    await queue.submit("second", blocked_task, name="second")
    await queue.stop_accepting()

    with pytest.raises(QueueShuttingDownError):
        await queue.submit("third", blocked_task, name="third")

    status = await queue.get_queue_status()
    assert status["accepting"] is False
    assert status["queued_tasks"] == ["second"]

    release.set()
    await asyncio.wait_for(queue.wait_for_completion(timeout=2), timeout=3)
    assert completed == ["first", "second"]


@pytest.mark.asyncio
async def test_zero_timeout_does_not_wait_indefinitely():
    queue = TaskQueue(max_concurrent_tasks=1, max_pending_tasks=1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_task():
        started.set()
        await release.wait()

    await queue.submit("blocked", blocked_task)
    await asyncio.wait_for(started.wait(), timeout=2)

    with pytest.raises(asyncio.TimeoutError):
        await queue.wait_for_completion(timeout=0)

    release.set()
    await asyncio.wait_for(queue.wait_for_completion(timeout=2), timeout=3)
