"""Cap reservation token must make ambiguous reserve and repeated rollback safe."""
from datetime import datetime

import pytest

from app.core.cap import redis_counter


class _AmbiguousRedis:
    def __init__(self):
        self.values = {}
        self.tokens = set()
        self.reserve_calls = 0
        self.rollback_calls = 0
        self.reserve_args = []

    async def eval(self, script, numkeys, *args):
        if script == redis_counter.RedisCapManager._RESERVE_LUA:
            self.reserve_calls += 1
            key, token_key, counter_ttl, initial, limit, token_ttl = args
            self.reserve_args.append((counter_ttl, token_ttl))
            if token_key in self.tokens:
                return int(self.values.get(key, 0))
            current = max(int(self.values.get(key, initial)), int(initial))
            if current >= int(limit):
                return -1
            self.values[key] = current + 1
            self.tokens.add(token_key)
            # 模拟 Redis 已执行 Lua，但响应在网络中丢失。
            raise OSError("simulated lost Redis response after execution")

        if script == redis_counter.RedisCapManager._ROLLBACK_RESERVATION_LUA:
            self.rollback_calls += 1
            key, token_key = args
            if token_key not in self.tokens:
                return 0
            # 与 Lua 保持一致：计数 key 丢失时保留 token，避免丢失恢复证据。
            if key not in self.values:
                return -2
            if self.values[key] <= 0:
                return -2
            self.tokens.remove(token_key)
            self.values[key] -= 1
            return self.values[key]

        raise AssertionError("unexpected Redis Lua script")


@pytest.mark.asyncio
async def test_total_cap_counter_has_no_ttl_but_reservation_token_expires(monkeypatch):
    calls = []

    class CaptureRedis:
        async def eval(self, script, numkeys, *args):
            assert script == redis_counter.RedisCapManager._RESERVE_LUA
            calls.append(args)
            return 1

    async def fake_get_redis_client():
        return CaptureRedis()

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter.settings, "CAP_FAIL_OPEN", False)

    result = await redis_counter.RedisCapManager.check_and_increment_total(
        offer_id=88,
        limit=500,
        publisher_id=9,
        initial_value=0,
        reservation_id="persistent-total-token",
    )

    assert result is True
    assert calls == [
        (
            redis_counter.get_total_cap_key(88, 9),
            f"{redis_counter.get_total_cap_key(88, 9)}:reservation:persistent-total-token",
            0,
            "0",
            "500",
            30 * 24 * 3600,
        )
    ]


@pytest.mark.asyncio
async def test_daily_cap_counter_and_reservation_keep_daily_ttl(monkeypatch):
    calls = []
    now = datetime(2026, 11, 10, 12, 0, 0)

    class CaptureRedis:
        async def eval(self, script, numkeys, *args):
            assert script == redis_counter.RedisCapManager._RESERVE_LUA
            calls.append(args)
            return 1

    async def fake_get_redis_client():
        return CaptureRedis()

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter, "get_app_now_naive", lambda: now)
    monkeypatch.setattr(redis_counter.settings, "CAP_FAIL_OPEN", False)

    result = await redis_counter.RedisCapManager.check_and_increment_daily(
        offer_id=88,
        limit=50,
        publisher_id=9,
        initial_value=0,
        reservation_id="daily-token",
    )

    assert result is True
    assert calls[0][2] == redis_counter.DEFAULT_EXPIRE_SECONDS
    assert calls[0][5] == redis_counter.DEFAULT_EXPIRE_SECONDS


def test_total_cap_reservation_script_persists_counter_without_expiry():
    script = redis_counter.RedisCapManager._RESERVE_LUA
    assert "local counter_ttl = tonumber(ARGV[1]) or 0" in script
    assert "redis.call('PERSIST', KEYS[1])" in script
    assert "redis.call('EXPIRE', KEYS[2], token_ttl)" in script


@pytest.mark.asyncio
async def test_ambiguous_daily_reservation_is_compensated_by_token(monkeypatch):
    redis = _AmbiguousRedis()
    now = datetime(2026, 11, 10, 12, 0, 0)

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter, "get_app_now_naive", lambda: now)
    monkeypatch.setattr(redis_counter.settings, "CAP_FAIL_OPEN", True)

    result = await redis_counter.RedisCapManager.check_and_increment_daily(
        offer_id=77,
        limit=100,
        publisher_id=12,
        initial_value=5,
        reservation_id="request-token-001",
    )

    key = redis_counter.get_daily_cap_key(77, now, 12)
    token_key = f"{key}:reservation:request-token-001"
    assert result is None
    assert redis.values[key] == 5
    assert token_key not in redis.tokens
    assert redis.reserve_calls == 1
    assert redis.rollback_calls == 1


@pytest.mark.asyncio
async def test_repeated_token_rollback_never_decrements_another_request(monkeypatch):
    redis = _AmbiguousRedis()
    now = datetime(2026, 11, 10, 12, 0, 0)
    key = redis_counter.get_daily_cap_key(77, now, 12)
    own_token = f"{key}:reservation:own"
    other_token = f"{key}:reservation:other"
    redis.values[key] = 2
    redis.tokens.update({own_token, other_token})

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter, "get_app_now_naive", lambda: now)

    first = await redis_counter.RedisCapManager.decrement_daily(
        77, 12, reservation_date=now, reservation_id="own"
    )
    second = await redis_counter.RedisCapManager.decrement_daily(
        77, 12, reservation_date=now, reservation_id="own"
    )

    assert first == 1
    assert second == 0  # token 已在第一次调用中删除，重复回滚不再扣减
    assert redis.values[key] == 1
    assert other_token in redis.tokens


@pytest.mark.asyncio
async def test_uncertain_reservation_with_failed_compensation_never_fail_opens(monkeypatch):
    class UnavailableForCompensation:
        async def eval(self, script, numkeys, *args):
            raise OSError("simulated Redis connection loss")

    async def fake_get_redis_client():
        return UnavailableForCompensation()

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter.settings, "CAP_FAIL_OPEN", True)

    with pytest.raises(RuntimeError, match="令牌补偿失败"):
        await redis_counter.RedisCapManager.check_and_increment_total(
            offer_id=77,
            limit=100,
            publisher_id=12,
            initial_value=5,
            reservation_id="request-token-uncertain",
        )


@pytest.mark.asyncio
async def test_redis_unavailable_fail_closed_is_not_reported_as_cap_exhausted(monkeypatch):
    async def no_redis():
        return None

    monkeypatch.setattr(redis_counter, "get_redis_client", no_redis)
    monkeypatch.setattr(redis_counter.settings, "CAP_FAIL_OPEN", False)

    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await redis_counter.RedisCapManager.check_and_increment_daily(
            offer_id=77,
            limit=100,
            publisher_id=12,
            initial_value=5,
        )


@pytest.mark.asyncio
async def test_legacy_rollback_without_reservation_token_never_decrements(monkeypatch):
    from app.core.cap import cap_manager

    calls = []

    async def capture(reservations):
        calls.append(reservations)

    monkeypatch.setattr(cap_manager, "_rollback_reserved_redis", capture)

    await cap_manager.rollback_cap_redis_counts(
        db=None,
        offer_id=77,
        publisher_id=12,
    )

    assert calls == []


@pytest.mark.asyncio
async def test_legacy_rollback_uses_only_explicit_reservation_tokens(monkeypatch):
    from app.core.cap import cap_manager

    reservations = [("daily", 77, 12, datetime(2026, 11, 10), "token-123")]
    calls = []

    async def capture(received):
        calls.append(received)

    monkeypatch.setattr(cap_manager, "_rollback_reserved_redis", capture)

    await cap_manager.rollback_cap_redis_counts(
        db=None,
        offer_id=77,
        publisher_id=12,
        reservations=reservations,
    )

    assert calls == [reservations]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    ["check_and_increment_daily", "check_and_increment_total"],
)
async def test_existing_token_with_evicted_counter_fails_closed(monkeypatch, method_name):
    class TokenSurvivedCounterEviction:
        async def eval(self, script, numkeys, *args):
            if script == redis_counter.RedisCapManager._RESERVE_LUA:
                # 模拟 token key 未被淘汰，但计数 key 已被 Redis 独立淘汰。
                return -2
            raise AssertionError("不应尝试无依据的计数回退")

    async def fake_get_redis_client():
        return TokenSurvivedCounterEviction()

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter.settings, "CAP_FAIL_OPEN", True)

    method = getattr(redis_counter.RedisCapManager, method_name)
    with pytest.raises(RuntimeError, match="计数 key 丢失"):
        await method(
            offer_id=77,
            limit=10,
            publisher_id=12,
            initial_value=9,
            reservation_id="already-reserved-token",
        )


def test_rollback_lua_preserves_token_when_counter_is_missing():
    # 脚本必须先确认计数 key 存在，再删除 reservation token。
    script = redis_counter.RedisCapManager._ROLLBACK_RESERVATION_LUA
    counter_check = script.index("if redis.call('EXISTS', KEYS[1]) == 0 then")
    token_delete = script.index("redis.call('DEL', KEYS[2])")
    assert counter_check < token_delete
    assert "return -2" in script



@pytest.mark.asyncio
async def test_rollback_keeps_reservation_token_when_counter_key_is_missing(monkeypatch):
    redis = _AmbiguousRedis()
    now = datetime(2026, 11, 10, 12, 0, 0)
    key = redis_counter.get_daily_cap_key(77, now, 12)
    token_key = f"{key}:reservation:orphaned-counter"
    redis.tokens.add(token_key)

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(redis_counter, "get_app_now_naive", lambda: now)

    result = await redis_counter.RedisCapManager.decrement_daily(
        77, 12, reservation_date=now, reservation_id="orphaned-counter"
    )

    assert result == -2
    assert token_key in redis.tokens
    assert key not in redis.values
