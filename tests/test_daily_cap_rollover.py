"""Daily Cap rollover must not erase counters already created for today."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.cap import cap_manager


@pytest.mark.asyncio
async def test_daily_reset_locks_rows_and_preserves_today_redis_key(monkeypatch):
    today = datetime(2026, 11, 10, 0, 0, 0)
    cap = SimpleNamespace(
        is_active=True,
        daily_cap=50,
        cap_start_date=datetime(2026, 11, 9, 0, 0, 0),
        current_daily_count=19,
    )

    class Scalars:
        def all(self):
            return [cap]

    class Result:
        def scalars(self):
            return Scalars()

    class FakeDB:
        def __init__(self):
            self.statement = None
            self.committed = False
            self.rolled_back = False

        async def execute(self, statement):
            self.statement = statement
            return Result()

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.rolled_back = True

    db = FakeDB()

    async def redis_must_not_be_touched():
        raise AssertionError("daily reset must not delete Redis today's counter")

    monkeypatch.setattr(cap_manager, "get_app_now_naive", lambda: datetime(2026, 11, 10, 12, 0, 0))
    monkeypatch.setattr(cap_manager, "get_redis_client", redis_must_not_be_touched)

    await cap_manager.reset_daily_caps(db)

    assert db.statement is not None
    assert db.statement._for_update_arg is not None
    assert db.committed is True
    assert db.rolled_back is False
    assert cap.current_daily_count == 0
    assert cap.cap_start_date == today


@pytest.mark.asyncio
async def test_daily_reset_uses_business_date_after_lock_wait_crosses_midnight(monkeypatch):
    # 模拟任务在 11 月 10 日启动，但取得行锁时已是 11 月 11 日。
    clock = {"now": datetime(2026, 11, 10, 23, 59, 59)}
    cap = SimpleNamespace(
        is_active=True,
        daily_cap=50,
        cap_start_date=datetime(2026, 11, 10, 0, 0, 0),
        current_daily_count=7,
    )
    events = []

    class Scalars:
        def all(self):
            return [cap]

    class Result:
        def scalars(self):
            return Scalars()

    class FakeDB:
        async def execute(self, statement):
            events.append("locked")
            # 行锁等待跨过午夜；业务日期必须在 execute 返回后读取。
            clock["now"] = datetime(2026, 11, 11, 0, 0, 3)
            return Result()

        async def commit(self):
            events.append("commit")

        async def rollback(self):
            events.append("rollback")

    def current_time():
        events.append("read_clock")
        return clock["now"]

    monkeypatch.setattr(cap_manager, "get_app_now_naive", current_time)

    await cap_manager.reset_daily_caps(FakeDB())

    assert events == ["locked", "read_clock", "commit"]
    assert cap.current_daily_count == 0
    assert cap.cap_start_date == datetime(2026, 11, 11, 0, 0, 0)
