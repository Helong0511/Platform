"""短链接点击计数 Redis 原子性回归测试。"""
from __future__ import annotations

import pytest

from app.core import short_link_click_counter as counter


@pytest.mark.asyncio
async def test_increment_uses_single_atomic_redis_script(monkeypatch):
    calls = []

    class FakeRedis:
        async def eval(self, script, number_of_keys, key):
            calls.append((script, number_of_keys, key))
            return 7

    async def fake_get_redis_client():
        return FakeRedis()

    monkeypatch.setattr(counter, "get_redis_client", fake_get_redis_client)
    await counter.increment_click_count_async("regression-code")

    assert len(calls) == 1
    script, number_of_keys, key = calls[0]
    assert number_of_keys == 1
    assert key == f"{counter.CLICK_COUNTER_PREFIX}regression-code"
    assert "EXPIRE" not in script
    assert "redis.call('INCR', KEYS[1])" in script
    assert "return redis.call('INCR', KEYS[1])" in script


def test_decrement_script_only_removes_counter_after_acknowledged_snapshot():
    # 待入账计数器不设置 TTL；确认入账后只扣减快照并在归零时删除。
    script = counter._DECREMENT_COUNTER_LUA
    assert "redis.call('DECRBY', KEYS[1], decrement)" in script
    assert "redis.call('SET'" not in script
    assert "redis.call('DEL', KEYS[1])" in script


@pytest.mark.asyncio
async def test_scan_counter_keys_deduplicates_scan_results():
    class FakeRedis:
        def __init__(self):
            self.calls = 0

        async def scan(self, cursor, match, count):
            self.calls += 1
            if self.calls == 1:
                return 1, ["short_link:click:a", "short_link:click:b"]
            return 0, ["short_link:click:b", "short_link:click:c"]

        async def keys(self, pattern):
            raise AssertionError("SCAN path must never fall back to KEYS")

    redis = FakeRedis()
    keys = await counter._scan_click_counter_keys(redis, max_keys=10)
    assert keys == [
        "short_link:click:a",
        "short_link:click:b",
        "short_link:click:c",
    ]


@pytest.mark.asyncio
async def test_scan_failure_does_not_fall_back_to_blocking_keys():
    class FakeRedis:
        def __init__(self):
            self.keys_called = False

        async def scan(self, cursor, match, count):
            raise OSError("simulated isolated Redis scan failure")

        async def keys(self, pattern):
            self.keys_called = True
            raise AssertionError("KEYS fallback is forbidden")

    redis = FakeRedis()
    keys = await counter._scan_click_counter_keys(redis, max_keys=10)
    assert keys == []
    assert redis.keys_called is False

@pytest.mark.asyncio
async def test_redis_recovery_flushes_local_snapshot_and_preserves_new_clicks(monkeypatch):
    async with counter._counter_lock:
        counter._click_counters.clear()
        counter._click_counters["recovery-code"] = 5

    class Result:
        def fetchall(self):
            return [("recovery-code", True)]

    class FakeDb:
        async def execute(self, statement):
            return Result()

    async def update_snapshot(db, short_code, count):
        assert short_code == "recovery-code"
        assert count == 5
        # 模拟数据库写入期间 Redis 仍不可用，新点击继续进入进程内计数器。
        async with counter._counter_lock:
            counter._click_counters[short_code] += 2
        return True

    monkeypatch.setattr(counter, "_update_click_count_with_retry", update_snapshot)
    synced = await counter._sync_in_memory_counters_to_db(FakeDb())

    assert synced == 1
    async with counter._counter_lock:
        assert counter._click_counters == {"recovery-code": 2}


@pytest.mark.asyncio
async def test_redis_recovery_keeps_local_counters_when_db_prevalidation_fails():
    async with counter._counter_lock:
        counter._click_counters.clear()
        counter._click_counters["recovery-db-error"] = 3

    class FakeDb:
        async def execute(self, statement):
            raise OSError("isolated database unavailable")

        async def rollback(self):
            return None

    synced = await counter._sync_in_memory_counters_to_db(FakeDb())

    assert synced == 0
    async with counter._counter_lock:
        assert counter._click_counters == {"recovery-db-error": 3}

@pytest.mark.asyncio
async def test_persist_empty_snapshot_clears_stale_file_atomically(tmp_path, monkeypatch):
    persist_file = tmp_path / "click_counters.json"
    persist_file.write_text('{"stale-code": 9}', encoding="utf-8")
    monkeypatch.setattr(counter, "COUNTER_PERSIST_FILE", persist_file)

    async with counter._counter_lock:
        counter._click_counters.clear()

    await counter.persist_counters()

    assert persist_file.exists()
    assert persist_file.read_text(encoding="utf-8") == "{}"
    assert list(tmp_path.glob("*.tmp")) == []

@pytest.mark.asyncio
async def test_redis_outage_sync_preserves_clicks_arriving_during_db_write(monkeypatch, tmp_path):
    async with counter._counter_lock:
        counter._click_counters.clear()
        counter._click_counters["outage-code"] = 4
    monkeypatch.setattr(counter, "COUNTER_PERSIST_FILE", tmp_path / "click_counters.json")

    class Result:
        def fetchall(self):
            return [("outage-code", True)]

    class FakeDb:
        async def execute(self, statement):
            return Result()

        async def rollback(self):
            return None

    async def no_redis():
        return None

    async def update_snapshot(db, short_code, count):
        assert (short_code, count) == ("outage-code", 4)
        async with counter._counter_lock:
            counter._click_counters[short_code] += 3
        return True

    monkeypatch.setattr(counter, "get_redis_client", no_redis)
    monkeypatch.setattr(counter, "_update_click_count_with_retry", update_snapshot)

    synced = await counter.sync_click_counts_to_db(FakeDb())

    assert synced == 1
    async with counter._counter_lock:
        assert counter._click_counters == {"outage-code": 3}
    assert '"outage-code": 3' in (tmp_path / "click_counters.json").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_sync_fails_closed_when_global_lock_acquisition_errors(monkeypatch):
    class BrokenRedis:
        async def set(self, *args, **kwargs):
            raise OSError("simulated isolated Redis lock failure")

    async def fake_get_redis_client():
        return BrokenRedis()

    class FakeDb:
        executed = False

        async def execute(self, statement):
            self.executed = True
            raise AssertionError("database sync must not run without the global lock")

    db = FakeDb()
    monkeypatch.setattr(counter, "get_redis_client", fake_get_redis_client)

    synced = await counter.sync_click_counts_to_db(db)

    assert synced == 0
    assert db.executed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_mode", ["unavailable", "increment_error", "client_error"])
async def test_click_increment_uses_atomic_db_fallback_across_workers(monkeypatch, redis_mode):
    class FakeResult:
        rowcount = 1

    class FakeDb:
        def __init__(self):
            self.statement = None
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, statement):
            self.statement = statement
            return FakeResult()

        async def commit(self):
            self.committed = True

    fake_db = FakeDb()

    def fake_session_local():
        return fake_db

    async def fake_invalidate(short_code):
        assert short_code == "worker-fallback-code"

    async def fake_get_redis_client():
        if redis_mode == "unavailable":
            return None
        if redis_mode == "client_error":
            raise OSError("simulated Redis client initialization failure")

        class BrokenRedis:
            async def eval(self, *args):
                raise OSError("simulated Redis increment failure")

        return BrokenRedis()

    monkeypatch.setattr(counter, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(counter, "invalidate_short_link_cache", fake_invalidate)

    await counter.increment_click_count_async("worker-fallback-code")

    assert fake_db.statement is not None
    assert fake_db.committed is True
    compiled = str(fake_db.statement)
    assert "click_count" in compiled


@pytest.mark.asyncio
async def test_sync_fails_closed_when_redis_client_lookup_raises(monkeypatch):
    async def broken_redis_client():
        raise OSError("simulated isolated Redis connection setup failure")

    class FakeDb:
        executed = False

        async def execute(self, statement):
            self.executed = True
            raise AssertionError("sync must not run without a verifiable distributed lock")

    db = FakeDb()
    monkeypatch.setattr(counter, "get_redis_client", broken_redis_client)

    synced = await counter.sync_click_counts_to_db(db)

    assert synced == 0
    assert db.executed is False


@pytest.mark.asyncio
async def test_db_prevalidation_failure_preserves_redis_click_counter(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.deleted = []
            self.eval_calls = 0

        async def set(self, *args, **kwargs):
            return True

        async def eval(self, script, number_of_keys, *args):
            self.eval_calls += 1
            # 第一处 eval 读取计数；finally 中的 eval 释放全局锁。
            return 5 if self.eval_calls == 1 else 1

        async def delete(self, key):
            self.deleted.append(key)
            return 1

    class BrokenDb:
        def __init__(self):
            self.execute_calls = 0
            self.rollback_calls = 0

        async def execute(self, statement, *args, **kwargs):
            self.execute_calls += 1
            raise OSError("simulated isolated database prevalidation failure")

        async def rollback(self):
            self.rollback_calls += 1

    redis = FakeRedis()
    db = BrokenDb()
    # 避免旧版故障恢复快照先触发一次独立的内存计数预验证。
    async with counter._counter_lock:
        counter._click_counters.clear()

    async def fake_get_redis_client():
        return redis

    async def fake_scan(redis_client, max_keys):
        return [f"{counter.CLICK_COUNTER_PREFIX}preserve-on-db-error"]

    monkeypatch.setattr(counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(counter, "_scan_click_counter_keys", fake_scan)

    synced = await counter.sync_click_counts_to_db(db)

    assert synced == 0
    assert db.execute_calls == 1
    assert db.rollback_calls == 1
    assert redis.deleted == []
