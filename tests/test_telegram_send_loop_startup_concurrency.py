"""Concurrent callers must share one fully running Telegram send event loop."""

import asyncio
import threading

from app.core.telegram import ptb_runtime


def test_concurrent_ensure_send_loop_creates_one_running_loop(monkeypatch):
    original_new_event_loop = asyncio.new_event_loop
    create_count = 0
    create_lock = threading.Lock()

    def counted_new_event_loop():
        nonlocal create_count
        with create_lock:
            create_count += 1
        return original_new_event_loop()

    monkeypatch.setattr(ptb_runtime.asyncio, "new_event_loop", counted_new_event_loop)
    monkeypatch.setattr(ptb_runtime, "_send_loop", None)
    monkeypatch.setattr(ptb_runtime, "_send_thread", None)
    monkeypatch.setattr(ptb_runtime, "_loop_start_lock", threading.Lock())
    ptb_runtime._SEND_LOOP_READY.clear()

    worker_count = 12
    barrier = threading.Barrier(worker_count)
    loops = []
    errors = []

    def worker():
        try:
            barrier.wait(timeout=3)
            loops.append(ptb_runtime.ensure_send_loop())
        except Exception as exc:  # pragma: no cover - assertion reports unexpected failure
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, name=f"send-loop-caller-{index}")
        for index in range(worker_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    try:
        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        assert len(loops) == worker_count
        assert create_count == 1
        assert all(loop is loops[0] for loop in loops)
        assert loops[0].is_running() is True

        async def identify_loop_thread():
            return threading.get_ident(), asyncio.get_running_loop()

        futures = [
            asyncio.run_coroutine_threadsafe(identify_loop_thread(), loops[0])
            for _ in range(worker_count)
        ]
        identities = [future.result(timeout=2) for future in futures]
        assert all(loop is loops[0] for _thread_id, loop in identities)
        assert all(
            thread_id == ptb_runtime._send_thread.ident
            for thread_id, _loop in identities
        )
    finally:
        loop = ptb_runtime._send_loop
        thread = ptb_runtime._send_thread
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=3)
        if loop is not None and not loop.is_closed():
            loop.close()
        monkeypatch.setattr(ptb_runtime, "_send_loop", None)
        monkeypatch.setattr(ptb_runtime, "_send_thread", None)
        ptb_runtime._SEND_LOOP_READY.clear()
