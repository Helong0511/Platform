"""点击归档必须保证归档完整后才删除源数据。"""
from datetime import datetime

import pytest

from app.services.tracking import clicks_archive_service as archive_module


class _Result:
    def __init__(self, *, scalar_value=None, rowcount=0):
        self._scalar_value = scalar_value
        self.rowcount = rowcount

    def scalar(self):
        return self._scalar_value


class _FakeDB:
    def __init__(self, *, total=2, inserted=2, deleted=2, insert_error=None):
        self.total = total
        self.inserted = inserted
        self.deleted = deleted
        self.insert_error = insert_error
        self.statements = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "SELECT COUNT(*)" in sql:
            return _Result(scalar_value=self.total)
        if "INSERT INTO `clicks_archive`" in sql:
            if self.insert_error:
                raise self.insert_error
            return _Result(rowcount=self.inserted)
        if "DELETE FROM `clicks`" in sql:
            return _Result(rowcount=self.deleted)
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_archive_commits_only_after_matching_insert_and_delete_counts(monkeypatch):
    service = archive_module.ClicksArchiveService()
    db = _FakeDB(total=2, inserted=2, deleted=2)
    monkeypatch.setattr(service, "should_skip_archive", _async_false)
    monkeypatch.setattr(service, "_ensure_archive_table", _async_noop)
    monkeypatch.setattr(
        archive_module, "get_app_now_naive",
        lambda: datetime(2026, 11, 22, 12, 0, 0),
    )

    result = await service.archive_old_clicks(db, days=90)

    insert_sql = next(sql for sql in db.statements if "INSERT INTO" in sql)
    assert "INSERT IGNORE" not in insert_sql
    assert insert_sql.count("`original_request_url`") == 2  # INSERT 目标列 + SELECT 来源列
    assert insert_sql.count("`final_redirect_url`") == 2  # INSERT 目标列 + SELECT 来源列
    assert "`original_request_url`" in archive_module._CREATE_ARCHIVE_TABLE_SQL
    assert "`final_redirect_url`" in archive_module._CREATE_ARCHIVE_TABLE_SQL
    assert db.committed is True
    assert db.rolled_back is False
    assert result["archived_count"] == 2
    assert result["deleted_count"] == 2


@pytest.mark.asyncio
async def test_archive_insert_failure_rolls_back_without_deleting_source(monkeypatch):
    service = archive_module.ClicksArchiveService()
    db = _FakeDB(insert_error=RuntimeError("simulated archive write failure"))
    monkeypatch.setattr(service, "should_skip_archive", _async_false)
    monkeypatch.setattr(service, "_ensure_archive_table", _async_noop)
    monkeypatch.setattr(
        archive_module, "get_app_now_naive",
        lambda: datetime(2026, 11, 22, 12, 0, 0),
    )

    with pytest.raises(RuntimeError, match="simulated archive write failure"):
        await service.archive_old_clicks(db, days=90)

    assert not any("DELETE FROM `clicks`" in sql for sql in db.statements)
    assert db.committed is False
    assert db.rolled_back is True


@pytest.mark.asyncio
async def test_archive_count_mismatch_rolls_back_without_deleting_source(monkeypatch):
    service = archive_module.ClicksArchiveService()
    db = _FakeDB(total=2, inserted=1, deleted=2)
    monkeypatch.setattr(service, "should_skip_archive", _async_false)
    monkeypatch.setattr(service, "_ensure_archive_table", _async_noop)
    monkeypatch.setattr(
        archive_module, "get_app_now_naive",
        lambda: datetime(2026, 11, 22, 12, 0, 0),
    )

    with pytest.raises(RuntimeError, match="数量不一致"):
        await service.archive_old_clicks(db, days=90)

    assert not any("DELETE FROM `clicks`" in sql for sql in db.statements)
    assert db.committed is False
    assert db.rolled_back is True


async def _async_false(*args, **kwargs):
    return False


async def _async_noop(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_archive_delete_count_mismatch_rolls_back_archive_insert(monkeypatch):
    service = archive_module.ClicksArchiveService()
    db = _FakeDB(total=2, inserted=2, deleted=1)
    monkeypatch.setattr(service, "should_skip_archive", _async_false)
    monkeypatch.setattr(service, "_ensure_archive_table", _async_noop)
    monkeypatch.setattr(
        archive_module, "get_app_now_naive",
        lambda: datetime(2026, 11, 22, 12, 0, 0),
    )

    with pytest.raises(RuntimeError, match="实际删除=1"):
        await service.archive_old_clicks(db, days=90)

    assert any("DELETE FROM `clicks`" in sql for sql in db.statements)
    assert db.committed is False
    assert db.rolled_back is True
