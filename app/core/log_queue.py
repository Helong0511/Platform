"""
进程内日志异步队列。

将文件 Handler 挂到 ``QueueListener`` 后台线程，业务线程只向 ``QueueHandler`` 投递，
降低请求路径上的磁盘 I/O 阻塞。多 Gunicorn worker 下仍是每进程一套队列；
跨进程安全继续依赖 ``SafeRotatingFileHandler`` 的轮转锁。

支持有界队列：满时丢弃新记录并计数，避免日志风暴撑爆内存。

注意：标准库 ``QueueHandler.prepare`` 会清空 ``exc_info``（为跨进程 pickle）。
本模块队列仅进程内使用，须保留异常信息，否则 Telegram 运行时错误通知会失效，
且 error.log 会误标 ``[no_exc_info]``。
"""
from __future__ import annotations

import atexit
import copy
import logging
import queue
import threading
import time
import traceback
from logging.handlers import QueueHandler, QueueListener
from typing import Any, Optional, Sequence, Union

from app.core.log_handlers import SafeStderrHandleErrorMixin

_listener: Optional[QueueListener] = None
_queue: Optional[Union[queue.SimpleQueue, queue.Queue]] = None
_atexit_registered = False
_dropped_count = 0
_drop_lock = threading.Lock()
_last_drop_warn_ts = 0.0


def is_log_queue_running() -> bool:
    return _listener is not None


def get_log_queue_stats() -> dict[str, Any]:
    """返回队列运行态（监控/测试用）。"""
    q = _queue
    qsize = None
    maxsize = None
    if q is not None:
        try:
            qsize = q.qsize()
        except Exception:
            qsize = None
        maxsize = getattr(q, "maxsize", None)
    with _drop_lock:
        dropped = _dropped_count
    usage_ratio = None
    if isinstance(maxsize, int) and maxsize > 0 and qsize is not None:
        usage_ratio = float(qsize) / float(maxsize)
    return {
        "running": _listener is not None,
        "qsize": qsize,
        "maxsize": maxsize if maxsize not in (None, 0) else None,
        "dropped": dropped,
        "usage_ratio": usage_ratio,
    }


def reset_log_queue_drop_count() -> None:
    global _dropped_count
    with _drop_lock:
        _dropped_count = 0


def _note_drop(n: int = 1) -> None:
    global _dropped_count, _last_drop_warn_ts
    with _drop_lock:
        _dropped_count += n
        total = _dropped_count
    now = time.time()
    # 最多约每 30 秒向真实 stderr 提示一次，避免再进日志队列
    if now - _last_drop_warn_ts >= 30:
        _last_drop_warn_ts = now
        try:
            import sys

            sys.__stderr__.write(
                f"[log_queue] 异步日志队列已满，已丢弃累计 {total} 条（当前 +{n}）\n"
            )
        except Exception:
            pass


class PlatformQueueHandler(SafeStderrHandleErrorMixin, QueueHandler):
    """
    进程内异步队列 Handler：保留 exc_info / exc_text。

    与标准 QueueHandler 不同：不清空异常字段，保证 listener 侧
    TelegramRuntimeErrorHandler 与 ErrorLogFormatter 行为正确。
    """

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:  # type: ignore[override]
        record = copy.copy(record)
        # 合并 args，避免 listener 线程上依赖易变对象
        try:
            if record.args:
                record.msg = record.getMessage()
                record.args = None
        except Exception:
            record.args = None
        # 预先生成 exc_text，作为兜底（即使后续某处清空 exc_info）
        if record.exc_info and not getattr(record, "exc_text", None):
            try:
                record.exc_text = "".join(traceback.format_exception(*record.exc_info))
            except Exception:
                try:
                    record.exc_text = logging.Formatter().formatException(record.exc_info)
                except Exception:
                    pass
        # 刻意保留 exc_info / stack_info（进程内队列无需 pickle）
        return record

    def enqueue(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        """record 已由 emit→prepare 处理，此处不再二次 prepare。"""
        self.queue.put_nowait(record)


class DroppingQueueHandler(PlatformQueueHandler):
    """有界队列满时丢弃，不阻塞业务线程。"""

    def enqueue(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            _note_drop(1)


def stop_log_queue_listener() -> None:
    """停止监听线程并关闭其上的 Handler（幂等）。"""
    global _listener, _queue
    listener = _listener
    _listener = None
    _queue = None
    if listener is None:
        return
    try:
        listener.stop()
    except Exception:
        pass
    for handler in getattr(listener, "handlers", ()) or ():
        try:
            handler.close()
        except Exception:
            pass


def start_log_queue_listener(
    handlers: Sequence[logging.Handler],
    *,
    maxsize: int = 20000,
) -> Union[queue.SimpleQueue, queue.Queue]:
    """
    启动（或重启）QueueListener。

    Args:
        handlers: 实际写盘/告警的 Handler 列表（由监听线程调用）
        maxsize: 队列上限；<=0 表示无界（SimpleQueue）

    Returns:
        供 QueueHandler 使用的队列
    """
    global _listener, _queue, _atexit_registered
    stop_log_queue_listener()
    handler_list = [h for h in handlers if h is not None]
    if maxsize and maxsize > 0:
        q: Union[queue.SimpleQueue, queue.Queue] = queue.Queue(maxsize=int(maxsize))
    else:
        q = queue.SimpleQueue()

    if not handler_list:
        _queue = q
        return q

    listener = QueueListener(q, *handler_list, respect_handler_level=True)
    listener.start()
    _listener = listener
    _queue = q

    if not _atexit_registered:
        atexit.register(shutdown_log_queue)
        _atexit_registered = True
    return q


def make_queue_handler(log_queue: Union[queue.SimpleQueue, queue.Queue]) -> QueueHandler:
    """创建投递到指定队列的 Handler（有界队列用丢弃策略）。"""
    if isinstance(log_queue, queue.Queue) and getattr(log_queue, "maxsize", 0) > 0:
        return DroppingQueueHandler(log_queue)
    return PlatformQueueHandler(log_queue)


def shutdown_log_queue(timeout_sec: float = 2.0) -> None:
    """
    生产关闭路径：尽力排空队列后停止 listener。

    lifespan / gunicorn worker_exit / atexit 应调用本函数，减少尾部日志丢失。
    """
    deadline = time.time() + max(0.05, float(timeout_sec))
    q = _queue
    while q is not None and time.time() < deadline:
        try:
            empty = q.empty()
        except Exception:
            break
        if empty:
            time.sleep(0.02)
            try:
                if q.empty():
                    break
            except Exception:
                break
        else:
            time.sleep(0.02)
    stop_log_queue_listener()


def flush_log_queue(timeout_sec: float = 1.0) -> None:
    """测试别名：同 ``shutdown_log_queue``（会停止 listener）。"""
    shutdown_log_queue(timeout_sec=timeout_sec)
