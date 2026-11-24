"""缓存标签失效的并发轮转、失败重试和崩溃恢复回归测试。"""
import pytest

from app.core import cache_manager


class FakeRedis:
    def __init__(self):
        self.sets = {
            f"{cache_manager.TAG_TO_KEYS_PREFIX}offer:7": {
                "cache:good",
                "cache:bad",
            }
        }
        self.deleted = []
        self.expiries = {}
        self.fail_key = "cache:bad"
        self.fail_srem_once = False
        self.inject_concurrent_add = False

    async def eval(self, script, numkeys, *args):
        if script == cache_manager._ADD_TAG_MEMBER_LUA:
            key, member, ttl = args
            self.sets.setdefault(key, set()).add(member)
            self.expiries[key] = int(ttl)
            return 1

        if script == cache_manager._ROTATE_TAG_BATCH_LUA:
            active_key, pending_key, batch_key = args
            if active_key in self.sets:
                self.sets[batch_key] = self.sets.pop(active_key)
                self.sets.setdefault(pending_key, set()).add(batch_key)
                # 模拟另一个请求在 Lua 轮转完成后立即向新活动集合写入。
                if self.inject_concurrent_add:
                    self.sets.setdefault(active_key, set()).add("cache:new")
            return list(self.sets.get(pending_key, set()))

        if script == cache_manager._FINALIZE_TAG_BATCH_LUA:
            batch_key, pending_key = args
            if self.sets.get(batch_key):
                return 0
            self.sets.pop(batch_key, None)
            self.sets.setdefault(pending_key, set()).discard(batch_key)
            if not self.sets[pending_key]:
                self.sets.pop(pending_key, None)
            return 1

        raise AssertionError("unexpected Lua script")

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def srem(self, key, member):
        if self.fail_srem_once:
            self.fail_srem_once = False
            raise RuntimeError("simulated SREM failure")
        members = self.sets.get(key, set())
        if member in members:
            members.remove(member)
            return 1
        return 0

    async def delete(self, key):
        if key == self.fail_key and self.fail_key:
            raise RuntimeError("simulated Redis delete failure")
        if key in self.deleted:
            return 0
        self.deleted.append(key)
        self.sets.pop(key, None)
        return 1

    async def scard(self, key):
        return len(self.sets.get(key, set()))


@pytest.fixture
def redis_client(monkeypatch):
    redis = FakeRedis()

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(cache_manager, "get_redis_client", fake_get_redis_client)
    return redis


@pytest.mark.asyncio
async def test_invalidate_by_tag_retains_failed_member_in_pending_batch(redis_client):
    redis = redis_client

    deleted = await cache_manager.CacheManager.invalidate_by_tag("offer:7")

    assert deleted == 1
    assert "cache:good" in redis.deleted
    assert "cache:bad" not in redis.deleted
    pending = redis.sets[f"{cache_manager.TAG_BATCHES_PREFIX}offer:7"]
    assert len(pending) == 1
    batch_key = next(iter(pending))
    assert redis.sets[batch_key] == {"cache:bad"}


@pytest.mark.asyncio
async def test_invalidate_by_tag_finalizes_batch_after_all_members_succeed(redis_client):
    redis = redis_client
    redis.fail_key = None

    deleted = await cache_manager.CacheManager.invalidate_by_tag("offer:7")

    assert deleted == 2
    assert "cache:good" in redis.deleted
    assert "cache:bad" in redis.deleted
    assert f"{cache_manager.TAG_BATCHES_PREFIX}offer:7" not in redis.sets


@pytest.mark.asyncio
async def test_concurrent_add_after_rotation_is_not_removed_with_old_batch(redis_client):
    redis = redis_client
    redis.fail_key = None
    redis.inject_concurrent_add = True

    deleted = await cache_manager.CacheManager.invalidate_by_tag("offer:7")

    active_key = f"{cache_manager.TAG_TO_KEYS_PREFIX}offer:7"
    assert deleted == 2
    assert redis.sets[active_key] == {"cache:new"}
    assert f"{cache_manager.TAG_BATCHES_PREFIX}offer:7" not in redis.sets


@pytest.mark.asyncio
async def test_invalidate_by_tag_recovers_pending_batch_after_worker_crash(redis_client):
    redis = redis_client
    redis.fail_key = None
    active_key = f"{cache_manager.TAG_TO_KEYS_PREFIX}offer:7"
    pending_key = f"{cache_manager.TAG_BATCHES_PREFIX}offer:7"
    batch_key = f"{cache_manager.TAG_BATCH_PREFIX}crashed-worker"
    redis.sets.pop(active_key)
    redis.sets[batch_key] = {"cache:orphan"}
    redis.sets[pending_key] = {batch_key}

    deleted = await cache_manager.CacheManager.invalidate_by_tag("offer:7")

    assert deleted == 1
    assert "cache:orphan" in redis.deleted
    assert pending_key not in redis.sets


@pytest.mark.asyncio
async def test_member_removal_failure_is_retried_idempotently(redis_client):
    redis = redis_client
    redis.fail_key = None
    redis.fail_srem_once = True

    first_deleted = await cache_manager.CacheManager.invalidate_by_tag("offer:7")
    pending_key = f"{cache_manager.TAG_BATCHES_PREFIX}offer:7"

    assert first_deleted == 2
    assert pending_key in redis.sets
    batch_key = next(iter(redis.sets[pending_key]))
    assert redis.sets[batch_key]

    second_deleted = await cache_manager.CacheManager.invalidate_by_tag("offer:7")

    assert second_deleted == 0
    assert pending_key not in redis.sets


@pytest.mark.asyncio
async def test_add_cache_tag_uses_atomic_add_and_expiry(redis_client):
    result = await cache_manager.CacheManager.add_cache_tag("cache:one", ["offer:7"])

    assert result is True
    tag_key = f"{cache_manager.TAG_TO_KEYS_PREFIX}offer:7"
    assert redis.sets[tag_key] == {"cache:good", "cache:bad", "cache:one"}
    assert redis.expiries[tag_key] == 7 * 24 * 3600
