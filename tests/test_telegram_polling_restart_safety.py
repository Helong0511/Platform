"""Telegram polling shutdown/restart must not leave a second live poller."""
import threading

import pytest

from app.core.telegram import polling_manager as manager
from app.core.telegram import file_lock


def test_stop_polling_uses_loop_threadsafe_stop_running(monkeypatch):
    called = []

    class FakeApplication:
        def stop_running(self):
            called.append("stop_running")

        async def stop(self):
            raise AssertionError("Application.stop must not be used to stop run_polling")

    class FakeLoop:
        def is_running(self):
            return True

        def call_soon_threadsafe(self, callback):
            callback()

    app = FakeApplication()
    monkeypatch.setattr(manager, "_active_application", app)
    monkeypatch.setattr(manager, "_polling_loop", FakeLoop())

    assert manager.stop_polling_application() is True
    assert called == ["stop_running"]


def test_restart_fails_closed_if_old_polling_thread_does_not_exit(monkeypatch):
    class StuckThread:
        name = "TelegramBot"

        def is_alive(self):
            return True

        def join(self, timeout=None):
            self.join_timeout = timeout

    thread = StuckThread()
    monkeypatch.setattr(threading, "enumerate", lambda: [thread])
    monkeypatch.setattr(manager, "stop_polling_application", lambda **_kwargs: True)
    monkeypatch.setattr(
        manager,
        "release_bot_lock",
        lambda: (_ for _ in ()).throw(AssertionError("must not release live thread lock")),
    )
    monkeypatch.setattr(
        manager,
        "start_bot_thread",
        lambda: (_ for _ in ()).throw(AssertionError("must not start a second poller")),
    )

    result = manager.restart_bot_thread(join_timeout=0)

    assert result == {
        "stopped": True,
        "thread_joined": False,
        "started": False,
        "restarted": False,
    }
    assert thread.join_timeout == 0


def test_os_lock_file_is_preserved_and_can_be_reacquired(tmp_path):
    file_lock.release_bot_lock()
    lock_path = tmp_path / "telegram_bot.lock"

    assert file_lock.acquire_bot_lock(lock_path) is True
    assert file_lock.is_lock_held() is True
    file_lock.release_bot_lock()

    assert lock_path.exists(), "释放 OS 锁后保留稳定 inode，不应 unlink"
    assert file_lock.is_lock_held() is False

    assert file_lock.acquire_bot_lock(lock_path) is True
    file_lock.release_bot_lock()


def test_active_pid_lock_metadata_never_expires_by_age(tmp_path, monkeypatch):
    lock_path = tmp_path / "telegram_bot.lock"
    lock_path.write_text(
        f"PID: {__import__('os').getpid()}\nTimestamp: 1\nHostname: test\n",
        encoding="utf-8",
    )

    assert file_lock._is_lock_expired(lock_path) is False


def test_lock_fails_closed_without_os_lock_support(tmp_path, monkeypatch):
    file_lock.release_bot_lock()
    monkeypatch.setattr(file_lock, "HAS_FCNTL", False)
    monkeypatch.setattr(file_lock, "HAS_MSVCRT", False)

    assert file_lock.acquire_bot_lock(tmp_path / "unsupported.lock") is False
    assert file_lock.is_lock_held() is False



def test_bot_lock_does_not_allow_same_process_reentry(tmp_path):
    file_lock.release_bot_lock()
    lock_path = tmp_path / "telegram_bot.lock"

    assert file_lock.acquire_bot_lock(lock_path) is True
    assert file_lock.acquire_bot_lock(lock_path) is False
    file_lock.release_bot_lock()



def test_restart_checks_all_existing_polling_threads(monkeypatch):
    class Thread:
        name = "TelegramBot"

        def __init__(self, exits):
            self.exits = exits
            self.joined = False

        def is_alive(self):
            return not (self.joined and self.exits)

        def join(self, timeout=None):
            self.joined = True

    first = Thread(exits=True)
    second = Thread(exits=False)
    monkeypatch.setattr(threading, "enumerate", lambda: [first, second])
    monkeypatch.setattr(manager, "stop_polling_application", lambda **_kwargs: True)
    monkeypatch.setattr(manager, "release_bot_lock", lambda: None)
    monkeypatch.setattr(manager, "start_bot_thread", lambda: True)

    result = manager.restart_bot_thread(join_timeout=0)

    assert first.joined is True
    assert second.joined is True
    assert result["thread_joined"] is False
    assert result["started"] is False
    assert result["restarted"] is False



def test_windows_msvcrt_lock_path_is_exercised_on_non_windows_ci(tmp_path, monkeypatch):
    import os

    calls = []

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(fd, mode, byte_count):
            calls.append((mode, byte_count, os.lseek(fd, 0, os.SEEK_CUR)))

    file_lock.release_bot_lock()
    monkeypatch.setattr(file_lock, "HAS_FCNTL", False)
    monkeypatch.setattr(file_lock, "HAS_MSVCRT", True)
    monkeypatch.setattr(file_lock, "msvcrt", FakeMsvcrt, raising=False)

    lock_path = tmp_path / "windows_style.lock"
    assert file_lock.acquire_bot_lock(lock_path) is True
    file_lock.release_bot_lock()

    assert calls == [
        (FakeMsvcrt.LK_NBLCK, 1, 0),
        (FakeMsvcrt.LK_UNLCK, 1, 0),
    ]
    assert lock_path.exists()



def test_kernel_flock_blocks_a_second_open_file_description(tmp_path):
    if not file_lock.HAS_FCNTL:
        pytest.skip("fcntl flock is unavailable on this platform")

    import fcntl

    file_lock.release_bot_lock()
    lock_path = tmp_path / "telegram_bot.lock"
    assert file_lock.acquire_bot_lock(lock_path) is True

    try:
        with open(lock_path, "a+b") as second_handle:
            with pytest.raises(BlockingIOError):
                fcntl.flock(
                    second_handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
    finally:
        file_lock.release_bot_lock()
