"""缓存失效 Outbox Worker 的确认与降级重试契约测试。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


class _RowsResult:
    def __init__(self, rows=None, rowcount=1):
        self._rows = rows or []
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session_factory(sessions):
    def factory():
        if not sessions:
            raise AssertionError("unexpected extra database session")
        return _SessionContext(sessions.pop(0))
    return factory


def _claimed_event(namespace="ad_data"):
    return SimpleNamespace(
        id=41,
        namespace=namespace,
        status="pending",
        attempt_count=0,
        max_attempts=12,
        locked_by=None,
        lease_token=None,
        lease_until=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("namespace", "expected_prefix"), [("ad_data", "ad_data:"), ("user_stats", "user_stats:")])
async def test_outbox_worker_marks_success_only_after_shared_store_confirmation(monkeypatch, namespace, expected_prefix):
    from app.core.infrastructure import cache_compat
    from app.services import cache_invalidation_outbox_worker as worker

    event = _claimed_event(namespace)
    claim_db = MagicMock()
    claim_db.execute = AsyncMock(side_effect=[
        _RowsResult(),
        _RowsResult(),
        _RowsResult([event]),
    ])
    claim_db.commit = AsyncMock()

    read_db = MagicMock()
    read_db.scalar = AsyncMock(return_value=event)

    finish_db = MagicMock()
    finish_db.execute = AsyncMock(return_value=_RowsResult(rowcount=1))
    finish_db.commit = AsyncMock()

    monkeypatch.setattr(
        worker,
        "AsyncSessionLocal",
        _session_factory([claim_db, read_db, finish_db]),
    )
    monkeypatch.setattr(
        cache_compat,
        "invalidate_cache_checked",
        AsyncMock(return_value=SimpleNamespace(
            operation_succeeded=True,
            shared_store_confirmed=True,
            error_code=None,
        )),
    )

    stats = await worker.process_cache_invalidation_outbox(batch_size=1)

    assert stats == {
        "claimed": 1,
        "success": 1,
        "retryable": 0,
        "failed": 0,
        "lease_lost": 0,
    }
    claim_db.commit.assert_awaited_once()
    finish_db.commit.assert_awaited_once()
    from app.core.infrastructure import cache_compat
    cache_compat.invalidate_cache_checked.assert_awaited_once_with(expected_prefix)


@pytest.mark.asyncio
async def test_outbox_worker_retries_local_memory_fallback_instead_of_marking_success(monkeypatch):
    from app.core.infrastructure import cache_compat
    from app.services import cache_invalidation_outbox_worker as worker

    event = _claimed_event()
    claim_db = MagicMock()
    claim_db.execute = AsyncMock(side_effect=[
        _RowsResult(),
        _RowsResult(),
        _RowsResult([event]),
    ])
    claim_db.commit = AsyncMock()

    read_db = MagicMock()
    read_db.scalar = AsyncMock(return_value=event)

    retry_db = MagicMock()
    retry_db.execute = AsyncMock(return_value=_RowsResult(rowcount=1))
    retry_db.commit = AsyncMock()

    monkeypatch.setattr(
        worker,
        "AsyncSessionLocal",
        _session_factory([claim_db, read_db, retry_db]),
    )
    invalidate = AsyncMock(return_value=SimpleNamespace(
        operation_succeeded=True,
        shared_store_confirmed=False,
        error_code="local_only",
    ))
    monkeypatch.setattr(cache_compat, "invalidate_cache_checked", invalidate)

    stats = await worker.process_cache_invalidation_outbox(batch_size=1)

    assert stats == {
        "claimed": 1,
        "success": 0,
        "retryable": 1,
        "failed": 0,
        "lease_lost": 0,
    }
    invalidate.assert_awaited_once_with("ad_data:")
    retry_db.commit.assert_awaited_once()
