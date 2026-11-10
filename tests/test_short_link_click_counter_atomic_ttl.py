"""短链接点击计数 Redis 原子性回归测试。"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.core import short_link_click_counter as counter


@pytest.mark.asyncio
async def test_increment_uses_single_atomic_redis_script(monkeypatch):
    calls = []

    class FakeRedis:
        async def eval(self, script, number_of_keys, counter_key, event_key, ttl):
            calls.append((script, number_of_keys, counter_key, event_key, ttl))
            return 7

    async def fake_get_redis_client():
        return FakeRedis()

    monkeypatch.setattr(counter, "get_redis_client", fake_get_redis_client)
    await counter.increment_click_count_async("regression-code")

    assert len(calls) == 1
    script, number_of_keys, key, event_key, ttl = calls[0]
    assert number_of_keys == 2
    assert key == f"{counter.CLICK_COUNTER_PREFIX}regression-code"
    assert event_key.startswith("short_link:click_event:")
    assert ttl == 120
    assert "EXPIRE" not in script
    # INCR 由 pcall 包装：只有 Redis 明确执行失败时才清除本次 marker，
    # 避免脚本异常或响应丢失造成相同 click_id 重试时重复计数。
    assert "pcall(redis.call, 'INCR', KEYS[1])" in script
    assert "if not ok then" in script
    assert "redis.call('DEL', KEYS[2])" in script
    assert "return incremented" in script


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
async def test_legacy_memory_snapshot_is_not_auto_replayed_without_batch_id():
    async with counter._counter_lock:
        counter._click_counters.clear()
        counter._click_counters["legacy-recovery-code"] = 5

    class FakeDb:
        executed = False

        async def execute(self, statement):
            self.executed = True
            raise AssertionError("legacy snapshot must not be replayed automatically")

    db = FakeDb()
    synced = await counter._sync_in_memory_counters_to_db(db)

    assert synced == 0
    assert db.executed is False
    async with counter._counter_lock:
        assert counter._click_counters == {"legacy-recovery-code": 5}


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
async def test_redis_outage_does_not_replay_legacy_non_idempotent_snapshot(monkeypatch):
    async with counter._counter_lock:
        counter._click_counters.clear()
        counter._click_counters["legacy-outage-code"] = 4

    class FakeDb:
        executed = False

        async def execute(self, statement):
            self.executed = True
            raise AssertionError("legacy local snapshot must not be flushed")

    async def no_redis():
        return None

    monkeypatch.setattr(counter, "get_redis_client", no_redis)
    db = FakeDb()
    synced = await counter.sync_click_counts_to_db(db)

    assert synced == 0
    assert db.executed is False
    async with counter._counter_lock:
        assert counter._click_counters == {"legacy-outage-code": 4}


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
@pytest.mark.parametrize("redis_mode", ["unavailable", "client_error"])
async def test_click_increment_uses_idempotent_db_fallback_across_workers(monkeypatch, redis_mode):
    class FakeResult:
        rowcount = 1

        def __init__(self, scalar=None, row=None):
            self.scalar = scalar
            self.row = row

        def scalar_one_or_none(self):
            return self.scalar

        def first(self):
            return self.row

    class FakeDb:
        def __init__(self):
            self.statement = None
            self.committed = False
            self.added = None
            self.ledger = set()
            self.ack_update = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, statement):
            self.statement = statement
            sql = str(statement).upper()
            if "FROM SHORT_LINK_CLICK_SYNC_BATCHES" in sql and sql.lstrip().startswith("SELECT"):
                return FakeResult(row=None)
            if "FROM SHORT_LINKS" in sql and sql.lstrip().startswith("SELECT"):
                return FakeResult(scalar=77)
            if sql.lstrip().startswith("UPDATE SHORT_LINKS"):
                return FakeResult()
            if sql.lstrip().startswith("UPDATE SHORT_LINK_CLICK_SYNC_BATCHES"):
                self.ack_update = True
                return FakeResult()
            raise AssertionError(f"unexpected DB statement: {sql}")

        def add(self, record):
            self.added = record

        async def flush(self):
            self.ledger.add(self.added.batch_id)

        async def commit(self):
            self.committed = True
            if self.ack_update and self.added is not None:
                self.added.acknowledged_at = True

    fake_db = FakeDb()

    def fake_session_local():
        return fake_db

    async def fake_invalidate(short_code):
        assert short_code == "worker-fallback-code"
        return True

    async def fake_get_redis_client():
        if redis_mode == "unavailable":
            return None
        if redis_mode == "client_error":
            raise OSError("simulated Redis client initialization failure")

    monkeypatch.setattr(counter, "AsyncSessionLocal", fake_session_local)
    monkeypatch.setattr(counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(counter, "invalidate_short_link_cache", fake_invalidate)

    await counter.increment_click_count_async(
        "worker-fallback-code",
        click_id="stable-db-fallback-event",
    )

    assert fake_db.statement is not None
    assert fake_db.committed is True
    assert fake_db.added is not None
    assert fake_db.added.short_code == "worker-fallback-code"
    assert fake_db.added.click_count == 1
    assert fake_db.added.acknowledged_at is not None
    assert fake_db.added.batch_id == counter.hashlib.sha256(
        b"stable-db-fallback-event"
    ).hexdigest()


@pytest.mark.asyncio
async def test_redis_recovery_checks_durable_db_fallback_event_before_increment(monkeypatch):
    event_digest = counter.hashlib.sha256(b"recovered-db-event").hexdigest()
    db_lookups = []
    reconciled = []

    class FakeResult:
        def first(self):
            return ("recovered-code", 1)

    class FakeDb:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, statement):
            db_lookups.append(str(statement))
            return FakeResult()

    class FakeRedis:
        async def exists(self, key):
            assert key == f"short_link:click_event:{event_digest}"
            return 0

        async def eval(self, *args):
            raise AssertionError("DB fallback duplicate must not execute Redis INCR")

    async def fake_reconcile(short_code, event_id_digest=None):
        reconciled.append((short_code, event_id_digest))
        return True

    monkeypatch.setattr(counter, "get_redis_client", lambda: _redis_async(FakeRedis()))
    monkeypatch.setattr(counter, "AsyncSessionLocal", FakeDb)
    monkeypatch.setattr(counter, "_increment_click_count_in_db", fake_reconcile)

    await counter.increment_click_count_async(
        "recovered-code",
        click_id="recovered-db-event",
    )

    assert db_lookups
    assert reconciled == [("recovered-code", event_digest)]


@pytest.mark.asyncio
async def test_redis_recovery_fails_closed_when_db_ledger_cannot_be_checked(monkeypatch):
    class FakeDb:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, statement):
            raise OSError("isolated DB ledger lookup failure")

    class FakeRedis:
        async def exists(self, key):
            return 0

        async def eval(self, *args):
            raise AssertionError("must not increment without durable dedupe check")

    monkeypatch.setattr(counter, "get_redis_client", lambda: _redis_async(FakeRedis()))
    monkeypatch.setattr(counter, "AsyncSessionLocal", FakeDb)

    await counter.increment_click_count_async(
        "recovery-fail-closed",
        click_id="recovery-db-error",
    )


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

    async def fake_scan(redis_client, max_keys, pattern=None):
        if pattern and ":pending:" in pattern:
            return []
        return [f"{counter.CLICK_COUNTER_PREFIX}preserve-on-db-error"]

    monkeypatch.setattr(counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(counter, "_scan_click_counter_keys", fake_scan)

    synced = await counter.sync_click_counts_to_db(db)

    assert synced == 0
    # 一次预验证失败；后续账本清理也因 DB 故障安全跳过。
    assert db.execute_calls == 2
    assert db.rollback_calls == 2
    assert redis.deleted == []


@pytest.mark.asyncio
async def test_ambiguous_redis_increment_error_does_not_double_write_database(monkeypatch):
    class BrokenRedis:
        async def eval(self, *args):
            raise OSError("simulated lost response after possible Redis execution")

    async def fake_get_redis_client():
        return BrokenRedis()

    def unexpected_session():
        raise AssertionError("ambiguous Redis outcome must not trigger a second DB increment")

    monkeypatch.setattr(counter, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(counter, "AsyncSessionLocal", unexpected_session)

    # 短链接跳转不应因计数设施的结果不确定而失败；但不能盲目双写。
    await counter.increment_click_count_async("ambiguous-redis-result")



def test_claim_batch_lua_atomically_moves_active_counter_without_ttl():
    script = counter._CLAIM_COUNTER_BATCH_LUA
    assert "redis.call('GET', KEYS[1])" in script
    assert "redis.call('SET', KEYS[2], count)" in script
    assert "redis.call('DEL', KEYS[1])" in script
    assert script.index("redis.call('SET', KEYS[2], count)") < script.index("redis.call('DEL', KEYS[1])")
    assert "'EX'" not in script
    assert "'PX'" not in script


class _LedgerResult:
    def __init__(self, value=None, rowcount=1):
        self.value = value
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self.value


class _ClickBatchLedgerDB:
    """模拟账本唯一键与 DB COMMIT 响应丢失；仅用于隔离单元测试。"""
    def __init__(self, *, ambiguous_first_commit=False):
        self.ledger = set()
        self.added = None
        self.click_updates = 0
        self.commits = 0
        self.ambiguous_first_commit = ambiguous_first_commit

    async def execute(self, statement):
        sql = str(statement)
        if "FROM short_links" in sql and sql.lstrip().upper().startswith("SELECT"):
            return _LedgerResult(17)
        if "FROM short_link_click_sync_batches" in sql and sql.lstrip().upper().startswith("SELECT"):
            # batch_id 参数由 SQLAlchemy 绑定；本测试只处理同一个 batch。
            return _LedgerResult(next(iter(self.ledger), None))
        if sql.lstrip().upper().startswith("UPDATE SHORT_LINKS"):
            self.click_updates += 1
            return _LedgerResult(rowcount=1)
        if sql.lstrip().upper().startswith("UPDATE SHORT_LINK_CLICK_SYNC_BATCHES"):
            return _LedgerResult(rowcount=1)
        raise AssertionError(f"unexpected SQL in fake DB: {sql}")

    def add(self, record):
        self.added = record

    async def flush(self):
        if self.added is not None:
            self.ledger.add(self.added.batch_id)

    async def commit(self):
        self.commits += 1
        if self.ambiguous_first_commit and self.commits == 1:
            # 模拟服务端已提交，但 COMMIT 响应丢失。
            raise OSError("ambiguous commit response")
        return None

    async def rollback(self):
        self.added = None


async def _redis_async(value):
    return value


async def _true_async():
    return True


class _PendingRedis:
    def __init__(self):
        self.deleted = []

    async def delete(self, key):
        self.deleted.append(key)
        return 1


@pytest.mark.asyncio
async def test_click_batch_replay_does_not_double_increment_after_ambiguous_commit(monkeypatch):
    monkeypatch.setattr(counter, "invalidate_short_link_cache", lambda _code: _true_async())
    db = _ClickBatchLedgerDB(ambiguous_first_commit=True)
    redis = _PendingRedis()
    args = dict(
        short_code="idempotent-code",
        batch_id="a" * 32,
        pending_key=f"{counter.CLICK_COUNTER_PREFIX}pending:idempotent-code:{'a' * 32}",
        click_count=9,
    )

    first_ok, first_inserted = await counter._process_pending_click_batch(db, redis, **args)
    assert first_ok is False
    assert first_inserted is False
    assert db.click_updates == 1
    assert args["pending_key"] not in redis.deleted

    second_ok, second_inserted = await counter._process_pending_click_batch(db, redis, **args)
    assert second_ok is True
    assert second_inserted is False
    assert db.click_updates == 1
    assert redis.deleted == [args["pending_key"]]



@pytest.mark.asyncio
async def test_click_batch_ack_failure_replays_without_double_increment(monkeypatch):
    monkeypatch.setattr(counter, "invalidate_short_link_cache", lambda _code: _true_async())
    db = _ClickBatchLedgerDB()
    pending_key = f"{counter.CLICK_COUNTER_PREFIX}pending:ack-retry-code:{'b' * 32}"

    class FailFirstDeleteRedis(_PendingRedis):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def delete(self, key):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("simulated lost Redis ACK")
            return await super().delete(key)

    redis = FailFirstDeleteRedis()
    args = dict(
        short_code="ack-retry-code",
        batch_id="b" * 32,
        pending_key=pending_key,
        click_count=4,
    )

    first_ok, first_inserted = await counter._process_pending_click_batch(db, redis, **args)
    assert first_ok is False
    assert first_inserted is True
    assert db.click_updates == 1
    assert args["batch_id"] in db.ledger

    second_ok, second_inserted = await counter._process_pending_click_batch(db, redis, **args)
    assert second_ok is True
    assert second_inserted is False
    assert db.click_updates == 1
    assert redis.deleted == [pending_key]



@pytest.mark.asyncio
async def test_click_batch_keeps_pending_until_cache_invalidation_succeeds(monkeypatch):
    state = {"invalidations": 0}

    async def invalidate(_short_code):
        state["invalidations"] += 1
        return state["invalidations"] > 1

    monkeypatch.setattr(counter, "invalidate_short_link_cache", invalidate)
    db = _ClickBatchLedgerDB()
    redis = _PendingRedis()
    args = dict(
        short_code="cache-recovery-code",
        batch_id="c" * 32,
        pending_key=f"{counter.CLICK_COUNTER_PREFIX}pending:cache-recovery-code:{'c' * 32}",
        click_count=3,
    )

    first_ok, first_inserted = await counter._process_pending_click_batch(db, redis, **args)
    assert first_ok is False
    assert first_inserted is True
    assert db.click_updates == 1
    assert args["batch_id"] in db.ledger
    assert args["pending_key"] not in redis.deleted

    second_ok, second_inserted = await counter._process_pending_click_batch(db, redis, **args)
    assert second_ok is True
    assert second_inserted is False
    assert db.click_updates == 1
    assert redis.deleted == [args["pending_key"]]


@pytest.mark.asyncio
async def test_legacy_raw_snapshot_batch_writer_fails_closed():
    with pytest.raises(RuntimeError, match="幂等恢复能力"):
        await counter.sync_click_counts_to_db_batch(
            db=None,
            updates=[("unsafe-legacy-code", 3)],
        )



def test_legacy_counter_snapshot_loader_rejects_invalid_entries(tmp_path, monkeypatch):
    snapshot = tmp_path / "click_counters.json"
    snapshot.write_text(
        '{"valid-code": 7, "negative": -1, "string-count": "4", "bool-count": true, "": 2}',
        encoding="utf-8",
    )
    monkeypatch.setattr(counter, "COUNTER_PERSIST_FILE", snapshot)
    counter._click_counters.clear()

    counter.load_persisted_counters()

    assert counter._click_counters == {"valid-code": 7}



@pytest.mark.asyncio
async def test_redis_increment_retry_uses_same_click_event_marker(monkeypatch):
    class AmbiguousRedis:
        def __init__(self):
            self.counter = {}
            self.markers = set()
            self.calls = []

        async def eval(self, script, numkeys, counter_key, event_key, ttl):
            self.calls.append((script, numkeys, counter_key, event_key, ttl))
            if event_key not in self.markers:
                self.markers.add(event_key)
                self.counter[counter_key] = self.counter.get(counter_key, 0) + 1
                if len(self.calls) == 1:
                    raise OSError("response lost after Redis executed Lua")
            return self.counter.get(counter_key, 0)

    redis = AmbiguousRedis()

    async def fake_redis():
        return redis

    monkeypatch.setattr(counter, "get_redis_client", fake_redis)
    await counter.increment_click_count_async("event-safe-code", click_id="stable-click-event")

    assert len(redis.calls) == 2
    assert redis.calls[0][1] == 2
    assert redis.calls[0][2] == redis.calls[1][2]
    assert redis.calls[0][3] == redis.calls[1][3]
    assert redis.calls[0][4] == 120
    assert redis.counter[redis.calls[0][2]] == 1
    assert "SET" in redis.calls[0][0] and "'NX'" in redis.calls[0][0]
    assert "INCR" in redis.calls[0][0]
    assert "pcall(redis.call, 'INCR'" in redis.calls[0][0]
    assert "redis.call('DEL', KEYS[2])" in redis.calls[0][0]


@pytest.mark.asyncio
async def test_redis_increment_retries_when_first_command_did_not_execute(monkeypatch):
    class RedisFailsBeforeExecute:
        def __init__(self):
            self.counter = {}
            self.markers = set()
            self.calls = 0

        async def eval(self, script, numkeys, counter_key, event_key, ttl):
            self.calls += 1
            if self.calls == 1:
                raise OSError("connection failed before command execution")
            if event_key not in self.markers:
                self.markers.add(event_key)
                self.counter[counter_key] = self.counter.get(counter_key, 0) + 1
            return self.counter[counter_key]

    redis = RedisFailsBeforeExecute()

    async def fake_redis():
        return redis

    monkeypatch.setattr(counter, "get_redis_client", fake_redis)
    await counter.increment_click_count_async("event-safe-code", click_id="event-before-exec")

    assert redis.calls == 2
    assert sum(redis.counter.values()) == 1


@pytest.mark.asyncio
async def test_ambiguous_redis_increment_does_not_blindly_fallback_to_db(monkeypatch):
    class RedisAlwaysFails:
        async def eval(self, *args):
            raise OSError("ambiguous Redis response")

    async def fake_redis():
        return RedisAlwaysFails()

    db_fallback_calls = []

    async def fake_db_fallback(short_code):
        db_fallback_calls.append(short_code)

    monkeypatch.setattr(counter, "get_redis_client", fake_redis)
    monkeypatch.setattr(counter, "_increment_click_count_in_db", fake_db_fallback)
    await counter.increment_click_count_async("event-safe-code", click_id="event-uncertain")

    assert db_fallback_calls == []



def test_all_redirect_paths_pass_stable_click_id_to_counter():
    source = Path("app/routes/short_link/handlers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "increment_click_count_async"
    ]

    assert len(calls) == 2
    assert all(
        any(keyword.arg == "click_id" for keyword in call.keywords)
        for call in calls
    )



@pytest.mark.asyncio
async def test_db_fallback_commit_response_loss_is_verified_by_event_ledger(monkeypatch):
    state = {"ledger": {}, "updates": 0, "commits": 0}
    invalidated = []

    class FakeResult:
        rowcount = 1

        def __init__(self, scalar=None, row=None):
            self.scalar = scalar
            self.row = row

        def scalar_one_or_none(self):
            return self.scalar

        def first(self):
            return self.row

    class FakeDb:
        def __init__(self):
            self.added = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, statement):
            sql = str(statement).upper()
            if "FROM SHORT_LINK_CLICK_SYNC_BATCHES" in sql and sql.lstrip().startswith("SELECT"):
                record = next(iter(state["ledger"].values()), None)
                return FakeResult(row=record)
            if "FROM SHORT_LINKS" in sql and sql.lstrip().startswith("SELECT"):
                return FakeResult(scalar=88)
            if sql.lstrip().startswith("UPDATE SHORT_LINKS"):
                state["updates"] += 1
                return FakeResult()
            raise AssertionError(f"unexpected DB statement: {sql}")

        def add(self, record):
            self.added = record

        async def flush(self):
            return None

        async def commit(self):
            state["commits"] += 1
            state["ledger"][self.added.batch_id] = (
                self.added.short_code,
                self.added.click_count,
            )
            if state["commits"] == 1:
                # DB 已提交，僅 COMMIT 回應遺失。
                raise OSError("ambiguous DB commit response")

    async def fake_redis():
        return None

    async def fake_invalidate(short_code):
        invalidated.append(short_code)

    monkeypatch.setattr(counter, "AsyncSessionLocal", FakeDb)
    monkeypatch.setattr(counter, "get_redis_client", fake_redis)
    monkeypatch.setattr(counter, "invalidate_short_link_cache", fake_invalidate)

    await counter.increment_click_count_async(
        "db-ambiguous-code",
        click_id="db-ambiguous-event",
    )

    assert state["updates"] == 1
    assert state["commits"] == 1
    assert len(state["ledger"]) == 1
    assert invalidated == ["db-ambiguous-code"]
