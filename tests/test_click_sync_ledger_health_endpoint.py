"""短链接点击刷盘账本监控 API 回归测试。"""

import ast
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.core import monitoring
from app.core.utils import get_app_now_naive


class _AggregateResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self.row = row
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _AggregateResult(self.row)


@pytest.mark.asyncio
async def test_click_sync_ledger_health_reports_empty_ledger_as_healthy():
    db = _FakeDB((0, None))

    result = await monitoring.get_click_sync_ledger_health(db)

    assert result["status"] == "healthy"
    assert result["unacknowledged_count"] == 0
    assert result["oldest_unacknowledged_at"] is None
    assert result["oldest_unacknowledged_age_seconds"] is None
    assert result["source"] == "mysql_ledger"
    sql = str(db.statement).lower()
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

        def fetchall(self):
            return _Rows().fetchall()

        def scalars(self):
            return _Scalars()

    class _DB:
        def __init__(self):
            self.statements = []
            self.committed = False

        async def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                return _Result("unacked")
            return _Result("other")

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
    for assignment in assignments:
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "get_app_now_naive"
            for node in ast.walk(assignment.value)
        )
