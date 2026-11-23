"""广告数据查询缓存 Generation / Outbox 事务契约测试。"""
from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.cache_invalidation_outbox import (
    CacheGenerationUnavailable,
    advance_cache_generation,
    get_cache_generation,
)


@pytest.mark.asyncio
async def test_get_cache_generation_reads_from_current_session():
    db = MagicMock()
    db.scalar = AsyncMock(return_value=17)

    assert await get_cache_generation(db) == 17
    db.scalar.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, 0, -1])
async def test_get_cache_generation_fails_closed_for_missing_or_invalid_value(value):
    db = MagicMock()
    db.scalar = AsyncMock(return_value=value)

    with pytest.raises(CacheGenerationUnavailable):
        await get_cache_generation(db)


@pytest.mark.asyncio
async def test_advance_generation_and_outbox_share_callers_transaction():
    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=1))
    db.scalar = AsyncMock(return_value=18)
    db.add = MagicMock()
    db.flush = AsyncMock()

    generation = await advance_cache_generation(db, namespace="ad_data")

    assert generation == 18
    event = db.add.call_args.args[0]
    assert event.namespace == "ad_data"
    assert event.generation == 18
    assert event.status == "pending"
    assert event.event_key == hashlib.sha256(b"ad_data:18").hexdigest()
    db.flush.assert_awaited_once()
    # 事务所有权属于业务调用方，登记服务不得自行提交。
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_advance_generation_fails_if_namespace_row_is_missing():
    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=0))
    db.add = MagicMock()
    db.flush = AsyncMock()

    with pytest.raises(CacheGenerationUnavailable):
        await advance_cache_generation(db)

    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_ad_data_get_or_set_uses_database_generation_in_cache_key(monkeypatch):
    from app.services.ad_data import query_cache

    db = MagicMock()
    db.scalar = AsyncMock(return_value=23)
    single_flight = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(query_cache, "get_or_set_single_flight", single_flight)

    result = await query_cache.ad_data_get_or_set(
        db,
        "ad_data:summary:abc",
        AsyncMock(return_value={"ok": True}),
        ttl=60,
    )

    assert result == {"ok": True}
    assert single_flight.await_args.args[0] == "ad_data:summary:abc:g23"
