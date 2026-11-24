"""Offer Redis 缓存三态读取回归测试。"""
import pytest

from app.core import offer_cache


class FakeRedis:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.deleted = []

    async def get(self, key):
        if self.error:
            raise self.error
        return self.value

    async def delete(self, key):
        self.deleted.append(key)
        return 1


@pytest.mark.asyncio
async def test_offer_cache_entry_distinguishes_cache_miss(monkeypatch):
    redis = FakeRedis()

    async def get_redis():
        return redis

    monkeypatch.setattr(offer_cache, "get_redis_client", get_redis)

    entry = await offer_cache.get_offer_cache_entry(17)

    assert entry.status == "miss"
    assert entry.advertiser_id is None


@pytest.mark.asyncio
async def test_offer_cache_entry_distinguishes_negative_cache(monkeypatch):
    redis = FakeRedis(offer_cache.NONE_MARKER)

    async def get_redis():
        return redis

    monkeypatch.setattr(offer_cache, "get_redis_client", get_redis)

    entry = await offer_cache.get_offer_cache_entry(17)

    assert entry.status == "negative"
    assert entry.advertiser_id is None


@pytest.mark.asyncio
async def test_offer_cache_entry_returns_advertiser_id(monkeypatch):
    redis = FakeRedis('{"offer_id": 17, "advertiser_id": 29}')

    async def get_redis():
        return redis

    monkeypatch.setattr(offer_cache, "get_redis_client", get_redis)

    entry = await offer_cache.get_offer_cache_entry(17)

    assert entry.status == "hit"
    assert entry.advertiser_id == 29


@pytest.mark.asyncio
async def test_offer_cache_entry_distinguishes_redis_failure(monkeypatch):
    redis = FakeRedis(error=RuntimeError("redis unavailable"))

    async def get_redis():
        return redis

    monkeypatch.setattr(offer_cache, "get_redis_client", get_redis)

    entry = await offer_cache.get_offer_cache_entry(17)

    assert entry.status == "unavailable"
    assert entry.advertiser_id is None


@pytest.mark.asyncio
async def test_offer_cache_entry_handles_missing_redis_client(monkeypatch):
    async def get_redis():
        return None

    monkeypatch.setattr(offer_cache, "get_redis_client", get_redis)

    entry = await offer_cache.get_offer_cache_entry(17)

    assert entry.status == "unavailable"


@pytest.mark.asyncio
async def test_legacy_offer_cache_api_remains_backward_compatible(monkeypatch):
    redis = FakeRedis('{"offer_id": 17, "advertiser_id": 29}')

    async def get_redis():
        return redis

    monkeypatch.setattr(offer_cache, "get_redis_client", get_redis)

    assert await offer_cache.get_offer_advertiser_id(17) == 29

    redis.value = offer_cache.NONE_MARKER
    assert await offer_cache.get_offer_advertiser_id(17) is None


@pytest.mark.asyncio
async def test_offer_warmup_is_disabled_for_write_only_cache():
    from app.core.cache_manager import CacheManager

    class NoQueryDB:
        async def execute(self, statement):
            raise AssertionError("unused Offer cache must not trigger database warmup queries")

    assert await CacheManager.warmup_offers(NoQueryDB()) == 0
