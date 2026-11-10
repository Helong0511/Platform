"""Fail-open Cap must never claim a Redis reservation that was not written."""
from types import SimpleNamespace

import pytest

from app.core.cap import cap_manager, redis_counter


class _BrokenRedis:
    async def eval(self, script, *args, **kwargs):
        if script == redis_counter.RedisCapManager._ROLLBACK_RESERVATION_LUA:
            # 模拟预留 Lua 未执行：令牌不存在，幂等补偿安全地返回未回退。
            return 0
        raise OSError("simulated Redis Lua failure")


@pytest.mark.asyncio
async def test_redis_lua_failure_open_returns_no_reservation(monkeypatch):
    async def fake_get_redis_client():
        return _BrokenRedis()

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter.settings, "CAP_FAIL_OPEN", True)

    result = await redis_counter.RedisCapManager.check_and_increment_daily(
        offer_id=77,
        limit=100,
        publisher_id=12,
        initial_value=5,
    )

    assert result is None


@pytest.mark.asyncio
async def test_fail_open_daily_failure_is_not_added_to_reservations(monkeypatch):
    cap = SimpleNamespace(
        offer_id=77,
        publisher_id=12,
        daily_cap=100,
        total_cap=1000,
        cap_start_date=None,
        current_daily_count=0,
        current_total_count=5,
    )

    class FakeDB:
        async def execute(self, statement):
            class Result:
                def scalars(self):
                    class Scalars:
                        def all(self):
                            return [cap]
                    return Scalars()
            return Result()

        async def flush(self):
            return None

    async def daily_fail_open(*args, **kwargs):
        return None

    async def total_reserved(*args, **kwargs):
        return True

    monkeypatch.setattr(cap_manager.settings, "CAP_FAIL_OPEN", True)
    from datetime import datetime
    business_now = datetime(2026, 11, 10, 12, 0, 0)
    monkeypatch.setattr(cap_manager, "get_app_now_naive", lambda: business_now)
    monkeypatch.setattr(
        cap_manager.RedisCapManager,
        "check_and_increment_daily",
        daily_fail_open,
    )
    monkeypatch.setattr(
        cap_manager.RedisCapManager,
        "check_and_increment_total",
        total_reserved,
    )

    ok, status, reservations = await cap_manager.increment_cap_count(
        db=FakeDB(),
        offer_id=77,
        publisher_id=12,
        include_reservations=True,
    )

    assert ok is True
    assert status == "cap_ok"
    assert len(reservations) == 1
    assert reservations[0][:4] == ("total", 77, 12, None)
    assert len(reservations[0][4]) == 32
    assert cap.current_daily_count == 1
    assert cap.cap_start_date == datetime(2026, 11, 10, 0, 0, 0)
    assert cap.current_total_count == 6
