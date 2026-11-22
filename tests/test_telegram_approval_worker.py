"""Telegram 审批有界 worker 池的容量、去重和背压测试。"""
import threading
import time

from app.core.telegram import approval_worker


def _wait_until_idle(timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if approval_worker.get_approval_worker_status()["pending_tasks"] == 0:
            return True
        time.sleep(0.01)
    return False


def test_approval_worker_pool_bounds_workers_and_rejects_overflow():
    release = threading.Event()
    started = []
    active = 0
    max_active = 0
    guard = threading.Lock()

    def processor(pending_id):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
            started.append(pending_id)
        try:
            release.wait(timeout=3.0)
        finally:
            with guard:
                active -= 1

    try:
        for pending_id in range(approval_worker.APPROVAL_MAX_IN_FLIGHT):
            assert approval_worker.submit_approval_task(
                pending_id, processor, pending_id
            ) == "submitted"

        assert approval_worker.submit_approval_task(0, processor, 0) == "duplicate"
        assert approval_worker.submit_approval_task(9999, processor, 9999) == "full"

        status = approval_worker.get_approval_worker_status()
        assert status["pending_tasks"] == approval_worker.APPROVAL_MAX_IN_FLIGHT
        assert status["queue_depth"] == (
            approval_worker.APPROVAL_MAX_IN_FLIGHT - status["active_workers"]
        )
        assert status["worker_limit"] == 4
        assert status["queue_capacity"] == 12
        assert status["active_workers"] <= approval_worker.APPROVAL_WORKER_COUNT
    finally:
        release.set()

    assert _wait_until_idle()
    assert max_active <= approval_worker.APPROVAL_WORKER_COUNT
    assert len(started) == approval_worker.APPROVAL_MAX_IN_FLIGHT





def test_approval_worker_shutdown_drains_active_and_cancels_queued_tasks():
    release = threading.Event()
    active_started = threading.Event()

    def blocking_processor(_pending_id):
        active_started.set()
        release.wait(timeout=3.0)

    try:
        for pending_id in range(approval_worker.APPROVAL_MAX_IN_FLIGHT):
            assert approval_worker.submit_approval_task(
                10000 + pending_id,
                blocking_processor,
                pending_id,
            ) == "submitted"

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if approval_worker.get_approval_worker_status()["active_workers"] == 4:
                break
            time.sleep(0.01)
        assert active_started.is_set()
        assert approval_worker.get_approval_worker_status()["active_workers"] == 4

        result = approval_worker.shutdown_approval_workers(timeout=0.05)
        assert result["cancelled"] == approval_worker.APPROVAL_QUEUE_CAPACITY
        assert result["remaining"] == approval_worker.APPROVAL_WORKER_COUNT
    finally:
        release.set()

    assert _wait_until_idle()


def test_approval_worker_rejects_new_tasks_after_shutdown_begins():
    assert approval_worker.submit_approval_task(7001, lambda: None) == "shutting_down"
    assert approval_worker.get_approval_worker_status()["accepting"] is False
