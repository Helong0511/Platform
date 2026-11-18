"""回归测试：Cap 同步和一致性检查不得覆盖并发预留或降低已确认计数。"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.cap import cap_sync, consistency_checker
from app.models.cap_reservation import CapReservation


class _ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class _RowsResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _FakeDB:
    def __init__(self, rows, *, pending_scopes=(), pending_ids=()):
        self.rows = rows
        self.pending_scopes = list(pending_scopes)
        self.pending_ids = list(pending_ids)
        self.query = None
        self.committed = False
        self.rolled_back = False

    async def execute(self, query):
        selected = list(query.selected_columns)
        if any(getattr(column, "table", None) is CapReservation.__table__ for column in selected):
            if len(selected) == 2:
                return _RowsResult(self.pending_scopes)
            return _ScalarResult(self.pending_ids)
        if self.query is None:
            self.query = query
        return _ScalarResult(self.rows)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _FakeRedis:
    def __init__(self, values):
        self.values = values
        self.writes = []
        self.reads = []

    async def get(self, key):
        self.reads.append(key)
        return self.values.get(key)

    async def setex(self, *args):
        self.writes.append(("setex", args))

    async def set(self, *args, **kwargs):
        self.writes.append(("set", args, kwargs))


@pytest.mark.asyncio
async def test_sync_all_caps_locks_rows_and_never_resets_existing_today_redis_key(monkeypatch):
    now = datetime(2026, 11, 10, 12, 0, 0)
    cap = SimpleNamespace(
        id=1,
        offer_id=77,
        publisher_id=12,
        daily_cap=100,
        total_cap=1000,
        cap_start_date=now - timedelta(days=1),
        current_daily_count=88,
        current_total_count=9,
        is_active=True,
    )
    daily_key = cap_sync.get_daily_cap_key(77, now, 12)
    total_key = cap_sync.get_total_cap_key(77, 12)
    redis = _FakeRedis({daily_key: "4", total_key: "5"})
    db = _FakeDB([cap])

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_sync, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_sync, "get_app_now_naive", lambda: now)

    stats = await cap_sync.CapSynchronizer(db).sync_all_active_caps()

    assert db.query._for_update_arg is not None
    assert str(db.query._order_by_clauses[0]) == "offer_caps.id ASC"
    assert stats == {"success": 1, "failed": 0, "skipped": 0}
    # 新业务日的 Redis key 已经包含真实预留，不能因为 DB 日期旧而被清零。
    assert cap.current_daily_count == 4
    assert cap.cap_start_date == now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Redis 回退时不能降低 DB 已确认的总计数。
    assert cap.current_total_count == 9
    assert redis.writes == []
    assert db.committed is True


@pytest.mark.asyncio
async def test_sync_single_cap_locks_row_and_keeps_maximum_count(monkeypatch):
    now = datetime(2026, 11, 10, 12, 0, 0)
    cap = SimpleNamespace(
        id=2,
        offer_id=78,
        publisher_id=None,
        daily_cap=20,
        total_cap=200,
        cap_start_date=now,
        current_daily_count=8,
        current_total_count=30,
    )
    redis = _FakeRedis({
        cap_sync.get_daily_cap_key(78, now, None): "6",
        cap_sync.get_total_cap_key(78, None): "25",
    })
    db = _FakeDB([cap])

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_sync, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_sync, "get_app_now_naive", lambda: now)

    assert await cap_sync.CapSynchronizer(db).sync_single_cap(2) is True
    assert db.query._for_update_arg is not None
    assert str(db.query._order_by_clauses[0]) == "offer_caps.id ASC"
    assert cap.current_daily_count == 8
    assert cap.current_total_count == 30
    assert db.committed is True


@pytest.mark.asyncio
async def test_consistency_fix_never_overwrites_redis_counters(monkeypatch):
    now = datetime(2026, 11, 10, 12, 0, 0)
    cap = SimpleNamespace(
        id=3,
        offer_id=79,
        publisher_id=13,
        daily_cap=50,
        total_cap=500,
        cap_start_date=now,
        current_daily_count=2,
        current_total_count=4,
        is_active=True,
    )
    daily_key = consistency_checker.get_daily_cap_key(79, now, 13)
    total_key = consistency_checker.get_total_cap_key(79, 13)
    redis = _FakeRedis({daily_key: "3", total_key: "5"})
    db = _FakeDB([cap])

    async def fake_redis():
        return redis

    monkeypatch.setattr(consistency_checker, "get_redis_client", fake_redis)
    monkeypatch.setattr(consistency_checker, "get_app_now_naive", lambda: now)

    issues = await consistency_checker.check_cap_consistency(
        db=db, offer_id=79, fix_inconsistencies=True
    )

    assert len(issues) == 1
    assert redis.writes == []
    assert any("未执行自动覆盖修复" in item for item in issues[0]["inconsistencies"])


@pytest.mark.asyncio
async def test_cleanup_does_not_assign_short_ttl_to_total_cap_keys(monkeypatch):
    class CleanupRedis:
        def __init__(self):
            self.expire_calls = []

        async def scan(self, cursor, match, count):
            if cursor == 0:
                return 0, [
                    "cpl:cap:total:77",
                    "cpl:cap:daily:77:2026-11-10",
                ]
            raise AssertionError("unexpected scan cursor")

        async def ttl(self, key):
            return -1

        async def expire(self, key, seconds):
            self.expire_calls.append((key, seconds))

    redis = CleanupRedis()

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_sync, "get_redis_client", fake_redis)
    cleaned = await cap_sync.CapSynchronizer(_FakeDB([])).cleanup_expired_caps()

    assert cleaned == 0
    assert redis.expire_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("daily_missing", "total_missing", "expected_issue"),
    [
        (True, False, "每日 Redis 计数 key 缺失"),
        (False, True, "总计 Redis 计数 key 缺失"),
        (True, True, "真实计数未知"),
    ],
)
async def test_missing_redis_cap_keys_are_unknown_not_zero_and_never_repaired(
    monkeypatch, daily_missing, total_missing, expected_issue
):
    now = datetime(2026, 11, 10, 12, 0, 0)
    cap = SimpleNamespace(
        id=4,
        offer_id=80,
        publisher_id=14,
        daily_cap=50,
        total_cap=500,
        cap_start_date=now,
        current_daily_count=0,
        current_total_count=0,
        is_active=True,
    )
    values = {}
    if not daily_missing:
        values[consistency_checker.get_daily_cap_key(80, now, 14)] = "0"
    if not total_missing:
        values[consistency_checker.get_total_cap_key(80, 14)] = "0"
    redis = _FakeRedis(values)
    db = _FakeDB([cap])

    async def fake_redis():
        return redis

    monkeypatch.setattr(consistency_checker, "get_redis_client", fake_redis)
    monkeypatch.setattr(consistency_checker, "get_app_now_naive", lambda: now)

    issues = await consistency_checker.check_cap_consistency(
        db=db, offer_id=80, fix_inconsistencies=True
    )

    assert len(issues) == 1
    issue = issues[0]
    assert expected_issue in " ".join(issue["inconsistencies"])
    assert issue["redis_daily_count"] == (None if daily_missing else 0)
    assert issue["redis_total_count"] == (None if total_missing else 0)
    assert issue["db_daily_count"] == 0
    assert issue["db_total_count"] == 0
    assert redis.writes == []
    assert any("未执行自动覆盖修复" in item for item in issue["inconsistencies"])



@pytest.mark.asyncio
async def test_sync_all_caps_reports_failure_when_commit_rolls_back_batch(monkeypatch):
    """DB commit 失败会回滚整批更新，统计不能继续报告逐行同步成功。"""
    now = datetime(2026, 11, 11, 12, 0, 0)
    cap = SimpleNamespace(
        id=9,
        offer_id=99,
        publisher_id=19,
        daily_cap=10,
        total_cap=100,
        cap_start_date=now,
        current_daily_count=1,
        current_total_count=2,
        is_active=True,
    )

    class FailingCommitDB(_FakeDB):
        async def commit(self):
            raise RuntimeError("simulated commit failure")

    db = FailingCommitDB([cap])
    redis = _FakeRedis({
        cap_sync.get_daily_cap_key(99, now, 19): "2",
        cap_sync.get_total_cap_key(99, 19): "3",
    })

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_sync, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_sync, "get_app_now_naive", lambda: now)

    stats = await cap_sync.CapSynchronizer(db).sync_all_active_caps()

    assert stats == {"success": 0, "failed": 1, "skipped": 0}
    assert db.rolled_back is True


@pytest.mark.asyncio
async def test_sync_all_caps_reports_missing_redis_counter_as_skipped(monkeypatch):
    now = datetime(2026, 11, 11, 12, 0, 0)
    cap = SimpleNamespace(
        id=10,
        offer_id=100,
        publisher_id=20,
        daily_cap=10,
        total_cap=100,
        cap_start_date=now,
        current_daily_count=4,
        current_total_count=9,
        is_active=True,
    )
    db = _FakeDB([cap])
    redis = _FakeRedis({
        cap_sync.get_daily_cap_key(100, now, 20): "8",
        # total key intentionally missing: unknown snapshot is not a successful sync.
    })

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_sync, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_sync, "get_app_now_naive", lambda: now)

    stats = await cap_sync.CapSynchronizer(db).sync_all_active_caps()

    assert stats == {"success": 0, "failed": 0, "skipped": 1}
    # Daily key 虽可读取，但 Total key 缺失时不提交该 Cap 的部分快照。
    assert cap.current_daily_count == 4
    assert cap.current_total_count == 9
    assert db.committed is True


@pytest.mark.asyncio
async def test_sync_all_caps_rolls_back_entire_batch_after_one_counter_read_fails(monkeypatch):
    now = datetime(2026, 11, 11, 12, 0, 0)
    caps = [
        SimpleNamespace(
            id=11, offer_id=101, publisher_id=21, daily_cap=10, total_cap=100,
            cap_start_date=now, current_daily_count=1, current_total_count=2,
            is_active=True,
        ),
        SimpleNamespace(
            id=12, offer_id=102, publisher_id=22, daily_cap=10, total_cap=100,
            cap_start_date=now, current_daily_count=3, current_total_count=4,
            is_active=True,
        ),
    ]

    class FailingRedis(_FakeRedis):
        async def get(self, key):
            if key == cap_sync.get_total_cap_key(102, 22):
                raise RuntimeError("redis read failed")
            return await super().get(key)

    db = _FakeDB(caps)
    redis = FailingRedis({
        cap_sync.get_daily_cap_key(101, now, 21): "2",
        cap_sync.get_total_cap_key(101, 21): "3",
        cap_sync.get_daily_cap_key(102, now, 22): "4",
    })

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_sync, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_sync, "get_app_now_naive", lambda: now)

    stats = await cap_sync.CapSynchronizer(db).sync_all_active_caps()

    assert stats == {"success": 0, "failed": 2, "skipped": 0}
    assert db.rolled_back is True
    assert db.committed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_counter", ["daily", "total"])
async def test_sync_single_cap_returns_false_and_rolls_back_when_counter_key_missing(
    monkeypatch, missing_counter
):
    now = datetime(2026, 11, 11, 12, 0, 0)
    cap = SimpleNamespace(
        id=21,
        offer_id=121,
        publisher_id=31,
        daily_cap=10,
        total_cap=100,
        cap_start_date=now - timedelta(days=1),
        current_daily_count=7,
        current_total_count=17,
    )
    values = {
        cap_sync.get_daily_cap_key(121, now, 31): "8",
        cap_sync.get_total_cap_key(121, 31): "18",
    }
    if missing_counter == "daily":
        values.pop(cap_sync.get_daily_cap_key(121, now, 31))
    else:
        values.pop(cap_sync.get_total_cap_key(121, 31))

    db = _FakeDB([cap])
    redis = _FakeRedis(values)

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_sync, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_sync, "get_app_now_naive", lambda: now)

    result = await cap_sync.CapSynchronizer(db).sync_single_cap(21)

    assert result is False
    assert db.rolled_back is True
    assert db.committed is False


@pytest.mark.asyncio
async def test_sync_all_skips_scope_with_unresolved_reservation(monkeypatch):
    """PREPARED/RESERVED/NEEDS_RECONCILIATION 不得把临时 Redis 计数固化到 DB。"""
    now = datetime(2026, 11, 12, 12, 0, 0)
    cap = SimpleNamespace(
        id=31,
        offer_id=131,
        publisher_id=41,
        daily_cap=10,
        total_cap=100,
        cap_start_date=now,
        current_daily_count=2,
        current_total_count=3,
        is_active=True,
    )
    redis = _FakeRedis({
        cap_sync.get_daily_cap_key(131, now, 41): "8",
        cap_sync.get_total_cap_key(131, 41): "9",
    })
    db = _FakeDB([cap], pending_scopes=[(131, 41)])

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_sync, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_sync, "get_app_now_naive", lambda: now)

    stats = await cap_sync.CapSynchronizer(db).sync_all_active_caps()

    assert stats == {"success": 0, "failed": 0, "skipped": 1}
    assert cap.current_daily_count == 2
    assert cap.current_total_count == 3
    assert redis.reads == []
    assert db.committed is True


@pytest.mark.asyncio
async def test_sync_single_cap_skips_scope_with_unresolved_reservation(monkeypatch):
    now = datetime(2026, 11, 12, 12, 0, 0)
    cap = SimpleNamespace(
        id=32,
        offer_id=132,
        publisher_id=None,
        daily_cap=10,
        total_cap=100,
        cap_start_date=now,
        current_daily_count=4,
        current_total_count=5,
    )
    redis = _FakeRedis({
        cap_sync.get_daily_cap_key(132, now, None): "8",
        cap_sync.get_total_cap_key(132, None): "9",
    })
    db = _FakeDB([cap], pending_ids=[999])

    async def fake_redis():
        return redis

    monkeypatch.setattr(cap_sync, "get_redis_client", fake_redis)
    monkeypatch.setattr(cap_sync, "get_app_now_naive", lambda: now)

    result = await cap_sync.CapSynchronizer(db).sync_single_cap(32)

    assert result is False
    assert cap.current_daily_count == 4
    assert cap.current_total_count == 5
    assert redis.reads == []
    assert db.rolled_back is True
