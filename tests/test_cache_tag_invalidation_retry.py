"""缓存标签失效失败时保留索引，确保残留缓存键可重试清理。"""
import pytest

from app.core import cache_manager


class FakeRedis:
    def __init__(self):
        self.members = {"cache:good", "cache:bad"}
        self.deleted = []
        self.fail_key = "cache:bad"
        self.tag_deleted = False

    async def smembers(self, key):
        assert key == f"{cache_manager.TAG_TO_KEYS_PREFIX}offer:7"
        return set(self.members)

    async def delete(self, key):
        if key == "cache:bad" and self.fail_key:
            raise RuntimeError("simulated Redis delete failure")
        self.deleted.append(key)
        if key == f"{cache_manager.TAG_TO_KEYS_PREFIX}offer:7":
            self.tag_deleted = True
        return 1


@pytest.mark.asyncio
async def test_invalidate_by_tag_retains_tag_when_any_member_delete_fails(monkeypatch):
    redis = FakeRedis()

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(cache_manager, "get_redis_client", fake_get_redis_client)

    deleted = await cache_manager.CacheManager.invalidate_by_tag("offer:7")

    assert deleted == 1
    assert "cache:good" in redis.deleted
    assert "cache:bad" not in redis.deleted
    assert not redis.tag_deleted


@pytest.mark.asyncio
async def test_invalidate_by_tag_removes_tag_after_all_member_deletes_succeed(monkeypatch):
    redis = FakeRedis()
    redis.fail_key = None

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(cache_manager, "get_redis_client", fake_get_redis_client)

    deleted = await cache_manager.CacheManager.invalidate_by_tag("offer:7")

    assert deleted == 2
    assert redis.tag_deleted
