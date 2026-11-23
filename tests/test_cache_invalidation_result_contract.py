"""严格缓存失效结果必须区分共享 Redis、内存降级与 Redis 命令失败。"""
import pytest

from app.core.infrastructure.cache import (
    MemoryCacheBackend,
    RedisCacheBackend,
)
from app.core.infrastructure import cache_compat


class FakeRedis:
    def __init__(self, *, fail_scan=False, fail_delete=False):
        self.keys = {"query_cache:ad_data:a", "query_cache:ad_data:b"}
        self.fail_scan = fail_scan
        self.fail_delete = fail_delete
        self.scan_calls = 0

    async def scan(self, cursor, match, count):
        self.scan_calls += 1
        if self.fail_scan:
            raise ConnectionError("redis scan unavailable")
        matched = sorted(key for key in self.keys if key.startswith("query_cache:ad_data:"))
        return 0, matched

    async def delete(self, *keys):
        if self.fail_delete:
            raise ConnectionError("redis delete unavailable")
        deleted = 0
        for key in keys:
            if key in self.keys:
                self.keys.remove(key)
                deleted += 1
        return deleted


@pytest.mark.asyncio
async def test_redis_checked_delete_confirms_shared_store_and_count():
    redis = FakeRedis()
    result = await RedisCacheBackend(redis).delete_pattern_checked(
        "query_cache:ad_data:*"
    )

    assert result.operation_succeeded is True
    assert result.shared_store_confirmed is True
    assert result.deleted_count == 2
    assert result.backend == "redis"
    assert result.error_code is None
    assert redis.keys == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["scan", "delete"])
async def test_redis_checked_delete_reports_command_failure(failure):
    redis = FakeRedis(
        fail_scan=failure == "scan",
        fail_delete=failure == "delete",
    )
    result = await RedisCacheBackend(redis).delete_pattern_checked(
        "query_cache:ad_data:*"
    )

    assert result.operation_succeeded is False
    assert result.shared_store_confirmed is False
    assert result.deleted_count == 0
    assert result.backend == "redis"
    assert result.error_code == "ConnectionError"


@pytest.mark.asyncio
async def test_redis_checked_delete_reports_missing_client():
    result = await RedisCacheBackend(None).delete_pattern_checked(
        "query_cache:ad_data:*"
    )

    assert result.operation_succeeded is False
    assert result.shared_store_confirmed is False
    assert result.error_code == "redis_unavailable"


@pytest.mark.asyncio
async def test_memory_checked_delete_is_explicitly_local_only():
    cache = MemoryCacheBackend()
    await cache.set("query_cache:ad_data:one", {"value": 1})

    result = await cache.delete_pattern_checked("query_cache:ad_data:*")

    assert result.operation_succeeded is True
    assert result.shared_store_confirmed is False
    assert result.deleted_count == 1
    assert result.backend == "memory"
    assert result.error_code == "local_only"


@pytest.mark.asyncio
async def test_compat_checked_invalidation_preserves_shared_store_status(monkeypatch):
    redis = FakeRedis()
    backend = RedisCacheBackend(redis)

    async def fake_get_backend():
        return backend

    monkeypatch.setattr(cache_compat, "get_cache_backend", fake_get_backend)
    result = await cache_compat.invalidate_cache_checked("ad_data:")

    assert result.shared_store_confirmed is True
    assert result.deleted_count == 2
    assert redis.keys == set()


@pytest.mark.asyncio
async def test_compat_checked_invalidation_does_not_treat_memory_as_shared_success(monkeypatch):
    backend = MemoryCacheBackend()

    async def fake_get_backend():
        return backend

    monkeypatch.setattr(cache_compat, "get_cache_backend", fake_get_backend)
    result = await cache_compat.invalidate_cache_checked("ad_data:")

    assert result.operation_succeeded is True
    assert result.shared_store_confirmed is False
    assert result.error_code == "local_only"
