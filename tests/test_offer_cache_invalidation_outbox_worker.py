"""Offer 热点缓存失效 Worker 的共享 Redis 确认与 fencing 测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


class _Result:
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


def _factory(sessions):
    def create():
        if not sessions:
            raise AssertionError("unexpected database session")
        return _SessionContext(sessions.pop(0))
    return create


def _event():
    return SimpleNamespace(
        id=7,
        offer_id=123,
        status="pending",
        attempt_count=0,
        max_attempts=12,
        locked_by=None,
        lease_token=None,
        lease_until=None,
    )


@pytest.mark.asyncio
async def test_worker_deletes_only_exact_offer_hot_key_and_confirms_with_fencing(monkeypatch):
    from app.services import offer_cache_invalidation_outbox_worker as worker

    event = _event()
    claim = MagicMock()
    claim.execute = AsyncMock(side_effect=[_Result(), _Result(), _Result([event])])
    claim.commit = AsyncMock()

    verify = MagicMock()
    verify.scalar = AsyncMock(return_value=event.id)

    finish = MagicMock()
    finish.execute = AsyncMock(return_value=_Result(rowcount=1))
    finish.commit = AsyncMock()

    class Redis:
        def __init__(self):
            self.deleted = []

        async def delete(self, key):
            self.deleted.append(key)
            return 1

    redis = Redis()
    monkeypatch.setattr(worker, "AsyncSessionLocal", _factory([claim, verify, finish]))
    monkeypatch.setattr(worker, "get_redis_client", AsyncMock(return_value=redis))

    stats = await worker.process_offer_cache_invalidation_outbox(batch_size=1)

    assert stats == {
        "claimed": 1,
        "success": 1,
        "retryable": 0,
        "failed": 0,
        "lease_lost": 0,
    }
    assert redis.deleted == ["offer:cache:123"]
    claim.commit.assert_awaited_once()
    finish.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_does_not_mark_success_when_redis_is_unavailable(monkeypatch):
    from app.services import offer_cache_invalidation_outbox_worker as worker

    event = _event()
    claim = MagicMock()
    claim.execute = AsyncMock(side_effect=[_Result(), _Result(), _Result([event])])
    claim.commit = AsyncMock()

    verify = MagicMock()
    verify.scalar = AsyncMock(return_value=event.id)

    retry = MagicMock()
    retry.execute = AsyncMock(return_value=_Result(rowcount=1))
    retry.commit = AsyncMock()

    monkeypatch.setattr(worker, "AsyncSessionLocal", _factory([claim, verify, retry]))
    monkeypatch.setattr(worker, "get_redis_client", AsyncMock(return_value=None))

    stats = await worker.process_offer_cache_invalidation_outbox(batch_size=1)

    assert stats == {
        "claimed": 1,
        "success": 0,
        "retryable": 1,
        "failed": 0,
        "lease_lost": 0,
    }
    retry.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_stops_before_redis_when_lease_fencing_token_is_lost(monkeypatch):
    from app.services import offer_cache_invalidation_outbox_worker as worker

    event = _event()
    claim = MagicMock()
    claim.execute = AsyncMock(side_effect=[_Result(), _Result(), _Result([event])])
    claim.commit = AsyncMock()

    verify = MagicMock()
    verify.scalar = AsyncMock(return_value=None)

    redis = AsyncMock()
    monkeypatch.setattr(worker, "AsyncSessionLocal", _factory([claim, verify]))
    monkeypatch.setattr(worker, "get_redis_client", redis)

    stats = await worker.process_offer_cache_invalidation_outbox(batch_size=1)

    assert stats == {
        "claimed": 1,
        "success": 0,
        "retryable": 0,
        "failed": 0,
        "lease_lost": 1,
    }
    redis.assert_not_awaited()
