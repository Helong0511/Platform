"""点击归档必须使用有界行锁批次，并保证每批归档完整后才删除源数据。"""
from datetime import datetime

import pytest

from app.services.tracking import clicks_archive_service as archive_module


class _Scalars:
    def __init__(self, values):
        self._values = list(values or [])

    def all(self):
        return self._values


class _Result:
    def __init__(self, *, scalar_value=None, rowcount=0, values=None):
        self._scalar_value = scalar_value
        self.rowcount = rowcount
        self._values = values

    def scalar(self):
        return self._scalar_value

    def scalars(self):
        return _Scalars(self._values)


class _FakeDB:
    def __init__(
        self,
        *,
        max_id=3,
        batches=None,
        inserted_counts=None,
        deleted_counts=None,
        insert_error_batch=None,
    ):
        self.max_id = max_id
        self.batches = list(batches or [])
        self.inserted_counts = list(inserted_counts or [])
        self.deleted_counts = list(deleted_counts or [])
        self.insert_error_batch = insert_error_batch
        self.select_calls = 0
        self.current_batch_index = -1
        self.current_ids = []
        self.statements = []
        self.parameters = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        self.parameters.append(dict(params or {}))

        if "SELECT MAX(`id`) FROM `clicks`" in sql:
            return _Result(scalar_value=self.max_id)

        if "FOR UPDATE" in sql and "FROM `clicks`" in sql:
            self.current_batch_index = self.select_calls
            self.current_ids = (
                self.batches[self.current_batch_index]
                if self.current_batch_index < len(self.batches)
                else []
            )
            self.select_calls += 1
            return _Result(values=self.current_ids)

        if "INSERT INTO `clicks_archive`" in sql:
            if self.insert_error_batch == self.current_batch_index + 1:
                raise RuntimeError("simulated archive write failure")
            count = (
                self.inserted_counts[self.current_batch_index]
                if self.current_batch_index < len(self.inserted_counts)
                else len(self.current_ids)
            )
            return _Result(rowcount=count)

        if "DELETE FROM `clicks`" in sql:
            count = (
                self.deleted_counts[self.current_batch_index]
                if self.current_batch_index < len(self.deleted_counts)
                else len(self.current_ids)
            )
            return _Result(rowcount=count)

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


async def _async_false(*args, **kwargs):
    return False


async def _async_noop(*args, **kwargs):
    return None


def _prepare_service(monkeypatch, db):
    service = archive_module.ClicksArchiveService()
    monkeypatch.setattr(service, "should_skip_archive", _async_false)
    monkeypatch.setattr(service, "_ensure_archive_table", _async_noop)
    monkeypatch.setattr(
        archive_module,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 22, 12, 0, 0),
    )
    return service, db


@pytest.mark.asyncio
async def test_archive_uses_bounded_locked_batches_and_commits_each_complete_batch(monkeypatch):
    db = _FakeDB(
        max_id=3,
        batches=[[1, 2], [3], []],
        inserted_counts=[2, 1],
        deleted_counts=[2, 1],
    )
    service, db = _prepare_service(monkeypatch, db)

    result = await service.archive_old_clicks(db, days=90, batch_size=2)

    select_sql = next(sql for sql in db.statements if "FOR UPDATE" in sql)
    insert_sql = next(sql for sql in db.statements if "INSERT INTO" in sql)
    assert "ORDER BY `click_time` ASC, `id` ASC" in select_sql
    assert "LIMIT :batch_size" in select_sql
    assert "FOR UPDATE" in select_sql
    assert "`id` <= :high_water_id" in select_sql
    assert insert_sql.count("`original_request_url`") == 2
    assert insert_sql.count("`final_redirect_url`") == 2
    assert "expanding" not in insert_sql.lower()  # expanding 参数由 SQLAlchemy 在执行时安全展开
    assert all(p.get("high_water_id") == 3 for p in db.parameters if "high_water_id" in p)
    assert all(p.get("batch_size") == 2 for p in db.parameters if "batch_size" in p)
    assert db.commit_count == 3  # 两个数据批次 + 结束时空批次
    assert db.rollback_count == 0
    assert result["archived_count"] == 3
    assert result["deleted_count"] == 3
    assert result["batch_count"] == 2
    assert result["high_water_id"] == 3


@pytest.mark.asyncio
async def test_archive_insert_failure_rolls_back_current_batch_without_deleting_source(monkeypatch):
    db = _FakeDB(max_id=2, batches=[[1, 2], []], insert_error_batch=1)
    service, db = _prepare_service(monkeypatch, db)

    with pytest.raises(RuntimeError, match="simulated archive write failure"):
        await service.archive_old_clicks(db, days=90, batch_size=2)

    assert not any("DELETE FROM `clicks`" in sql for sql in db.statements)
    assert db.commit_count == 0
    assert db.rollback_count == 1


@pytest.mark.asyncio
async def test_archive_insert_count_mismatch_rolls_back_without_deleting_source(monkeypatch):
    db = _FakeDB(max_id=2, batches=[[1, 2], []], inserted_counts=[1])
    service, db = _prepare_service(monkeypatch, db)

    with pytest.raises(RuntimeError, match="待归档=2，实际写入=1"):
        await service.archive_old_clicks(db, days=90, batch_size=2)

    assert not any("DELETE FROM `clicks`" in sql for sql in db.statements)
    assert db.commit_count == 0
    assert db.rollback_count == 1


@pytest.mark.asyncio
async def test_archive_delete_count_mismatch_rolls_back_current_batch(monkeypatch):
    db = _FakeDB(max_id=2, batches=[[1, 2], []], deleted_counts=[1])
    service, db = _prepare_service(monkeypatch, db)

    with pytest.raises(RuntimeError, match="实际删除=1"):
        await service.archive_old_clicks(db, days=90, batch_size=2)

    assert any("DELETE FROM `clicks`" in sql for sql in db.statements)
    assert db.commit_count == 0
    assert db.rollback_count == 1


@pytest.mark.asyncio
async def test_archive_failure_after_prior_commit_keeps_completed_batches_resumable(monkeypatch):
    db = _FakeDB(
        max_id=3,
        batches=[[1, 2], [3], []],
        inserted_counts=[2, 1],
        deleted_counts=[2, 1],
        insert_error_batch=2,
    )
    service, db = _prepare_service(monkeypatch, db)

    with pytest.raises(RuntimeError, match="simulated archive write failure"):
        await service.archive_old_clicks(db, days=90, batch_size=2)

    delete_statements = [sql for sql in db.statements if "DELETE FROM `clicks`" in sql]
    assert len(delete_statements) == 1  # 第二批写入失败，不执行第二批删除
    assert db.commit_count == 1  # 第一批已完整提交
    assert db.rollback_count == 1  # 仅回滚失败的第二批


@pytest.mark.asyncio
async def test_archive_empty_source_returns_without_batch_work(monkeypatch):
    db = _FakeDB(max_id=None)
    service, db = _prepare_service(monkeypatch, db)

    result = await service.archive_old_clicks(db, days=90)

    assert result["archived_count"] == 0
    assert result["deleted_count"] == 0
    assert result["batch_count"] == 0
    assert db.rollback_count == 1


@pytest.mark.parametrize("days", [0, -1, True, 1.5])
@pytest.mark.asyncio
async def test_archive_rejects_invalid_retention_days_before_database_work(monkeypatch, days):
    db = _FakeDB()
    service, db = _prepare_service(monkeypatch, db)

    with pytest.raises(ValueError, match="days"):
        await service.archive_old_clicks(db, days=days)

    assert db.statements == []


@pytest.mark.parametrize("batch_size", [0, -1, 10_001, True, 1.5])
@pytest.mark.asyncio
async def test_archive_rejects_invalid_batch_size_before_database_work(monkeypatch, batch_size):
    db = _FakeDB()
    service, db = _prepare_service(monkeypatch, db)

    with pytest.raises(ValueError, match="batch_size"):
        await service.archive_old_clicks(db, days=90, batch_size=batch_size)

    assert db.statements == []
