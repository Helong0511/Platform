"""点击记录备用直写的 click_id 幂等回归测试。"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.api_v1.tracking import tracking


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeSession:
    def __init__(self, existing_id=None, commit_error=None):
        self.existing_id = existing_id
        self.commit_error = commit_error
        self.added = []
        self.execute_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        self.execute_calls += 1
        return _Result(self.existing_id)

    def add(self, record):
        self.added.append(record)

    async def commit(self):
        self.commit_calls += 1
        if self.commit_error:
            raise self.commit_error

    async def rollback(self):
        self.rollback_calls += 1


@pytest.mark.asyncio
async def test_existing_click_id_is_skipped_without_regenerating(monkeypatch):
    session = _FakeSession(existing_id=55)

    monkeypatch.setattr(tracking, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        tracking,
        "regenerate_click_id_from_click_data",
        lambda data: (_ for _ in ()).throw(AssertionError("must not regenerate click_id")),
    )

    await tracking.create_click_background({"click_id": "same-event-id"})

    assert session.execute_calls == 1
    assert session.added == []
    assert session.commit_calls == 0
    assert session.rollback_calls == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_insert_is_idempotent_success(monkeypatch):
    duplicate = IntegrityError(
        "INSERT INTO clicks",
        {},
        Exception("Duplicate entry 'same-event-id' for key 'clicks.click_id'"),
    )
    session = _FakeSession(existing_id=None, commit_error=duplicate)

    monkeypatch.setattr(tracking, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        tracking,
        "regenerate_click_id_from_click_data",
        lambda data: (_ for _ in ()).throw(AssertionError("must not regenerate click_id")),
    )

    await tracking.create_click_background({"click_id": "same-event-id"})

    assert len(session.added) == 1
    assert session.commit_calls == 1
    assert session.rollback_calls == 1
