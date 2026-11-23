"""短链接点击刷盘账本监控 API 回归测试。"""

import ast
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import monitoring
from app.core.utils import get_app_now_naive


class _AggregateResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _StateResult:
    def __init__(self, state):
        self.state = state

    def scalar_one_or_none(self):
        return self.state


class _FakeDB:
    def __init__(self, row, cleanup_state=None):
        self.row = row
        self.cleanup_state = cleanup_state or SimpleNamespace(
            status="healthy",
            consecutive_failure_count=0,
            total_failure_count=0,
            last_attempt_at=None,
            last_success_at=None,
            last_failure_at=None,
            last_error_type=None,
            last_unacked_scanned_count=0,
            last_acknowledged_count=0,
            last_deleted_count=0,
            last_redis_check_failures=0,
            last_cache_invalidation_failures=0,
        )
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _AggregateResult(self.row)
        return _StateResult(self.cleanup_state)


@pytest.mark.asyncio
async def test_click_sync_ledger_health_reports_empty_ledger_as_healthy():
    db = _FakeDB((0, None))

    result = await monitoring.get_click_sync_ledger_health(db)

    assert result["status"] == "healthy"
    assert result["unacknowledged_count"] == 0
    assert result["oldest_unacknowledged_at"] is None
    assert result["oldest_unacknowledged_age_seconds"] is None
    assert result["source"] == "mysql_ledger"
    assert result["cleanup"]["status"] == "healthy"
    sql = str(db.statements[0]).lower()
    assert "short_link_click_sync_batches" in sql
    assert "acknowledged_at is null" in sql


@pytest.mark.asyncio
async def test_click_sync_ledger_health_reports_oldest_unacknowledged_age():
    oldest = get_app_now_naive() - timedelta(minutes=15)
    db = _FakeDB((3, oldest))

    result = await monitoring.get_click_sync_ledger_health(db)

    assert result["status"] == "backlog"
    assert result["unacknowledged_count"] == 3
    assert datetime.fromisoformat(result["oldest_unacknowledged_at"]).tzinfo is not None
    assert 14 * 60 <= result["oldest_unacknowledged_age_seconds"] <= 16 * 60
    assert result["source"] == "mysql_ledger"
    assert result["cleanup"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_click_sync_ledger_health_reports_persistent_cleanup_failures():
    failure_time = get_app_now_naive() - timedelta(minutes=3)
    state = SimpleNamespace(
        status="degraded",
        consecutive_failure_count=2,
        total_failure_count=7,
        last_attempt_at=get_app_now_naive(),
        last_success_at=get_app_now_naive() - timedelta(hours=1),
        last_failure_at=failure_time,
        last_error_type="redis_exists:ConnectionError",
        last_unacked_scanned_count=4,
        last_acknowledged_count=1,
        last_deleted_count=12,
        last_redis_check_failures=2,
        last_cache_invalidation_failures=0,
    )
    result = await monitoring.get_click_sync_ledger_health(_FakeDB((0, None), state))
    assert result["status"] == "degraded"
    assert result["cleanup"]["status"] == "degraded"
    assert result["cleanup"]["consecutive_failure_count"] == 2
    assert result["cleanup"]["total_failure_count"] == 7
    assert result["cleanup"]["last_error_type"] == "redis_exists:ConnectionError"
    assert datetime.fromisoformat(result["cleanup"]["last_failure_at"]).tzinfo is not None


@pytest.mark.asyncio
async def test_click_sync_ledger_health_does_not_hide_database_errors():
    class BrokenDB:
        async def execute(self, statement):
            raise OSError("database unavailable")

    with pytest.raises(OSError, match="database unavailable"):
        await monitoring.get_click_sync_ledger_health(BrokenDB())


@pytest.mark.asyncio
async def test_click_sync_ledger_cleanup_log_redacts_exception_text(caplog):
    from app.core import short_link_click_counter as counter

    class BrokenDB:
        async def execute(self, statement):
            raise OSError("password=must-not-appear")

        async def rollback(self):
            return None

    await counter._cleanup_click_sync_batch_ledger(BrokenDB(), object())

    assert "error_type=OSError" in caplog.text
    assert "must-not-appear" not in caplog.text
    assert "password=" not in caplog.text


@pytest.mark.asyncio
async def test_click_sync_ledger_cleanup_uses_application_timezone_for_ack_and_retention(monkeypatch):
    from app.core import short_link_click_counter as counter

    fixed_now = datetime(2026, 11, 23, 12, 34, 56)
    monkeypatch.setattr(counter, "get_app_now_naive", lambda: fixed_now)

    class _Rows:
        def fetchall(self):
            return [("batch-id", "short-code")]

    class _Scalars:
        def all(self):
            return []

    class _Result:
        def __init__(self, kind):
            self.kind = kind
            self.rowcount = 1

        def fetchall(self):
            return _Rows().fetchall()

        def scalars(self):
            return _Scalars()

        def scalar_one_or_none(self):
            return None

    class _DB:
        def __init__(self):
            self.statements = []
            self.committed = False

        async def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                return _Result("unacked")
            return _Result("other")

        def add(self, _state):
            return None

        async def commit(self):
            self.committed = True

        async def rollback(self):
            raise AssertionError("unexpected rollback")

    class _Redis:
        async def exists(self, key):
            return 0

    async def invalidate(_short_code):
        return True

    monkeypatch.setattr(counter, "invalidate_short_link_cache", invalidate)
    db = _DB()

    await counter._cleanup_click_sync_batch_ledger(db, _Redis())

    assert db.committed is True
    # 第二条 SQL 是 ACK 补记；第三条 SQL 是已 ACK 历史记录清理查询。
    ack_params = db.statements[1].compile().params
    retention_params = db.statements[2].compile().params
    assert fixed_now in ack_params.values()
    assert fixed_now - timedelta(days=30) in retention_params.values()



def test_all_click_sync_ledger_ack_timestamps_use_application_timezone():
    source = Path("app/core/short_link_click_counter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments = [
        keyword
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "values"
        for keyword in node.keywords
        if keyword.arg == "acknowledged_at"
    ]

    assert len(assignments) == 3
    direct_helper_calls = [
        assignment
        for assignment in assignments
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "get_app_now_naive"
            for node in ast.walk(assignment.value)
        )
    ]
    assert len(direct_helper_calls) == 2

    # 批量清理路径在函数开始时固定一次应用时区时间，再复用该快照。
    assert any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "now" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "get_app_now_naive"
        for node in ast.walk(tree)
    )
    assert any(
        isinstance(assignment.value, ast.Name) and assignment.value.id == "now"
        for assignment in assignments
    )
