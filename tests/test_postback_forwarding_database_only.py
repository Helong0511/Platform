"""Postback Publisher/Product 查询不再写入没有读取者的旁路缓存。"""
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
        self.execute = AsyncMock(return_value=_Result(value))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("getter", "entity"),
    [
        (
            cache_manager.CacheManager.get_cached_publisher,
            SimpleNamespace(id=17, postback_url="https://example.invalid/publisher"),
        ),
        (
            cache_manager.CacheManager.get_cached_product,
            SimpleNamespace(
                id=23,
                downstream_postback_url="https://example.invalid/product",
            ),
        ),
    ],
)
async def test_postback_publisher_and_product_getters_are_database_only(
    monkeypatch, getter, entity
):
    db = _DB(entity)
    cache_backend = AsyncMock()
    get_backend = AsyncMock(return_value=cache_backend)
    monkeypatch.setattr(cache_manager, "get_cache_backend", get_backend)

    result = await getter(entity.id, db)

    assert result is entity
    db.execute.assert_awaited_once()
    get_backend.assert_not_awaited()
    cache_backend.set.assert_not_awaited()
    cache_backend.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_postback_offer_getter_remains_database_authoritative():
    offer = SimpleNamespace(id=31, advertiser_id=202, offer_name="current")
    db = _DB(offer)

    result = await cache_manager.CacheManager.get_cached_offer(offer.id, db)

    assert result is offer
    assert result.advertiser_id == 202
    db.execute.assert_awaited_once()
