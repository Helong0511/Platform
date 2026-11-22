"""Telegram Postback 审批有界工作池。

每个进程限制活跃 worker 和排队任务总数；数据库状态仍是最终业务事实，
内存队列只负责短期执行调度，不替代持久化 pending 记录。
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, wait
from typing import Any, Callable

logger = logging.getLogger(__name__)

APPROVAL_WORKER_COUNT = 4
APPROVAL_QUEUE_CAPACITY = 12
APPROVAL_MAX_IN_FLIGHT = APPROVAL_WORKER_COUNT + APPROVAL_QUEUE_CAPACITY
APPROVAL_SHUTDOWN_DRAIN_SECONDS = 8.0

_lock = threading.RLock()
_executor = ThreadPoolExecutor(
    max_workers=APPROVAL_WORKER_COUNT,
    thread_name_prefix="TelegramPostbackApproval",
)
_accepting = True
_pending_ids: set[int] = set()
_futures: dict[int, Future] = {}
_active_workers = 0
_completed_count = 0
_failed_count = 0
_rejected_count = 0


def _run_task(
    processor: Callable[..., Any],
    args: tuple[Any, ...],
    submitted_at: float,
    pending_id: int,
) -> None:
    """执行单个审批任务并记录排队、执行耗时。"""
    global _active_workers
    started_at = time.monotonic()
    with _lock:
        _active_workers += 1
        active_workers = _active_workers
    logger.info(
        "Telegram 审批任务开始：pending_id=%s queue_wait_ms=%s active_workers=%s",
        pending_id,
        int((started_at - submitted_at) * 1000),
        active_workers,
    )
    try:
        processor(*args)
    finally:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        with _lock:
            _active_workers -= 1
            active_workers = _active_workers
        logger.info(
            "Telegram 审批任务执行结束：pending_id=%s duration_ms=%s active_workers=%s",
            pending_id,
            duration_ms,
            active_workers,
        )


def _task_done(pending_id: int, future: Future) -> None:
    """回收任务槽位，记录未被业务函数处理的意外异常。"""
    global _completed_count, _failed_count
    try:
        error = future.exception()
    except CancelledError:
        error = None
    with _lock:
        _pending_ids.discard(pending_id)
        _futures.pop(pending_id, None)
        if error is None:
            if not future.cancelled():
                _completed_count += 1
        else:
            _failed_count += 1
        pending_count = len(_pending_ids)
        active_workers = _active_workers
        queue_depth = max(0, pending_count - active_workers)
        completed_count = _completed_count
        failed_count = _failed_count
        rejected_count = _rejected_count
    if error is not None:
        logger.error(
            "Telegram 审批 worker 出现未处理异常：pending_id=%s error_type=%s",
            pending_id,
            type(error).__name__,
        )
    logger.info(
        "Telegram 审批队列状态：pending_tasks=%s queue_depth=%s active_workers=%s completed=%s failed=%s rejected=%s",
        pending_count,
        queue_depth,
        active_workers,
        completed_count,
        failed_count,
        rejected_count,
    )


def submit_approval_task(
    pending_id: int,
    processor: Callable[..., Any],
    *args: Any,
) -> str:
    """提交审批任务，返回 submitted / duplicate / full / shutting_down。"""
    global _rejected_count
    submitted_at = time.monotonic()
    with _lock:
        if not _accepting:
            _rejected_count += 1
            return "shutting_down"
        if pending_id in _pending_ids:
            return "duplicate"
        if len(_pending_ids) >= APPROVAL_MAX_IN_FLIGHT:
            _rejected_count += 1
            return "full"

        _pending_ids.add(pending_id)
        try:
            future = _executor.submit(
                _run_task,
                processor,
                args,
                submitted_at,
                pending_id,
            )
        except Exception as exc:
            _pending_ids.discard(pending_id)
            _rejected_count += 1
            logger.error(
                "提交 Telegram 审批任务失败：pending_id=%s error_type=%s",
                pending_id,
                type(exc).__name__,
            )
            return "full"

        _futures[pending_id] = future
        future.add_done_callback(lambda completed: _task_done(pending_id, completed))
        return "submitted"


def get_approval_worker_status() -> dict[str, int | bool]:
    """提供可观测的 worker/队列状态，不暴露任务参数或用户数据。"""
    with _lock:
        return {
            "accepting": _accepting,
            "active_workers": _active_workers,
            "pending_tasks": len(_pending_ids),
            "queue_depth": max(0, len(_pending_ids) - _active_workers),
            "worker_limit": APPROVAL_WORKER_COUNT,
            "queue_capacity": APPROVAL_QUEUE_CAPACITY,
            "completed": _completed_count,
            "failed": _failed_count,
            "rejected": _rejected_count,
        }


def shutdown_approval_workers(
    timeout: float = APPROVAL_SHUTDOWN_DRAIN_SECONDS,
) -> dict[str, int]:
    """停止接收任务，等待在途任务有限时间；超时后取消尚未开始的排队任务。"""
    global _accepting
    with _lock:
        _accepting = False
        futures = list(_futures.values())

    done, not_done = wait(futures, timeout=max(0.0, timeout))
    cancelled = 0
    for future in not_done:
        if future.cancel():
            cancelled += 1

    # wait=False 避免在 ASGI lifespan 关闭路径上无限阻塞。
    # 正在执行的任务依赖数据库/HTTP 超时自然退出；未开始的任务仍保持 pending 状态。
    _executor.shutdown(wait=False, cancel_futures=True)

    with _lock:
        remaining = len(_pending_ids)
    logger.warning(
        "Telegram 审批 worker 关闭：completed_before_timeout=%s cancelled_queued=%s remaining=%s",
        len(done),
        cancelled,
        remaining,
    )
    return {
        "completed": len(done),
        "cancelled": cancelled,
        "remaining": remaining,
    }
