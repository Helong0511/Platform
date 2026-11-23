"""短链接点击刷盘账本监控 API 回归测试。"""

from datetime import datetime, timedelta

from app.core.utils import get_app_now_naive

import pytest

from app.core import monitoring


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
