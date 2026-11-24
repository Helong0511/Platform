"""Postback 转发 Offer 缓存不能覆盖数据库权威字段。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.postback.forwarding import cache_manager


class _Scalars:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _Result:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return _Scalars(self.value)


class _DB:
    def __init__(self, value):
        self.value = value
        self.execute = AsyncMock(return_value=_Result(value))


@pytest.mark.asyncio
async def test_get_cached_offer_returns_database_entity_without_applying_stale_snapshot(monkeypatch):
    offer = SimpleNamespace(
        id=17,
        advertiser_id=202,
        offer_name="current-name",
    )
    db = _DB(offer)

    result = await cache_manager.CacheManager.get_cached_offer(17, db)

    assert result is offer
    assert result.advertiser_id == 202
    assert result.offer_name == "current-name"
    db.execute.assert_awaited_once()
