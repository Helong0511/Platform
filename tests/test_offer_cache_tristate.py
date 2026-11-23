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
@pytest.mark.parametrize("status", ["negative", "unavailable"])
async def test_offer_warmup_does_not_rewrite_negative_or_unavailable_cache(
    monkeypatch, status
):
    from types import SimpleNamespace

    from app.core import cache_manager

    offer = SimpleNamespace(id=17, advertiser_id=None, offer_name="test offer")

    class Scalars:
        def all(self):
            return [offer]

    class Result:
        def scalars(self):
            return Scalars()

    class FakeDB:
        async def execute(self, statement):
            return Result()

    async def get_entry(offer_id):
        assert offer_id == 17
        return offer_cache.OfferCacheEntry(status=status)

    async def set_cache(*args, **kwargs):
        raise AssertionError("不应覆盖负缓存或在 Redis 故障时回填")

    monkeypatch.setattr(cache_manager, "get_offer_cache_entry", get_entry)
    monkeypatch.setattr(cache_manager, "set_offer_cache", set_cache)

    assert await cache_manager.CacheManager.warmup_offers(FakeDB()) == 0


@pytest.mark.asyncio
async def test_offer_warmup_only_writes_on_confirmed_cache_miss(monkeypatch):
    from types import SimpleNamespace

    from app.core import cache_manager

    offer = SimpleNamespace(id=17, advertiser_id=29, offer_name="test offer")
    written = []

    class Scalars:
        def all(self):
            return [offer]

    class Result:
        def scalars(self):
            return Scalars()

    class FakeDB:
        async def execute(self, statement):
            return Result()

    async def get_entry(offer_id):
        return offer_cache.OfferCacheEntry(status="miss")

    async def set_cache(*args, **kwargs):
        written.append((args, kwargs))
        return True

    monkeypatch.setattr(cache_manager, "get_offer_cache_entry", get_entry)
    monkeypatch.setattr(cache_manager, "set_offer_cache", set_cache)

    assert await cache_manager.CacheManager.warmup_offers(FakeDB()) == 1
    assert len(written) == 1
