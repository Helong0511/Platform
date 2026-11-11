"""Redis Cap recovery must reconcile an existing stale key with the DB fallback count."""
import pytest

from app.core.cap import redis_counter


class _StatefulRedis:
    def __init__(self, initial_value):
        self.value = initial_value
        self.calls = []

    async def eval(self, script, numkeys, key, token_key, counter_ttl, db_count, limit, token_ttl):
        self.calls.append(
            (script, numkeys, key, token_key, counter_ttl, db_count, limit, token_ttl)
        )
        # Model the Lua reconciliation rule against an already-existing Redis key.
        current = max(self.value, int(db_count))
        if current >= int(limit):
            return -1
        self.value = current + 1
        return self.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "key_kind"),
    [
        ("check_and_increment_daily", "daily"),
        ("check_and_increment_total", "total"),
    ],
)
async def test_existing_redis_key_is_reconciled_to_db_fallback_count(
    monkeypatch, method_name, key_kind
):
    redis = _StatefulRedis(initial_value=2)

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)
    method = getattr(redis_counter.RedisCapManager, method_name)

    allowed = await method(
        offer_id=901,
        limit=20,
        publisher_id=33,
        initial_value=7,
    )

    assert allowed is True
    assert redis.value == 8
    assert len(redis.calls) == 1
    script, numkeys, key, token_key, counter_ttl, db_count, limit, token_ttl = redis.calls[0]
    assert numkeys == 2
    assert ":reservation:" in token_key
    assert key.startswith(f"cpl:cap:{key_kind}:901:")
    assert db_count == "7"
    assert limit == "20"
    assert counter_ttl == (
        redis_counter.DEFAULT_EXPIRE_SECONDS if key_kind == "daily" else 0
    )
    assert token_ttl == (
        redis_counter.DEFAULT_EXPIRE_SECONDS if key_kind == "daily" else 30 * 24 * 3600
    )
    assert "math.max(current, db_count)" in script
    assert "if not current then" in script


@pytest.mark.asyncio
async def test_recreated_cap_uses_existing_total_counter_when_db_baseline_is_zero(monkeypatch):
    """删除配置再按相同 Offer/渠道重建时，不能因新行计数为 0 覆盖 Redis 历史总计数。"""
    redis = _StatefulRedis(initial_value=17)

    async def fake_get_redis_client():
        return redis

    monkeypatch.setattr(redis_counter, "get_redis_client", fake_get_redis_client)

    allowed = await redis_counter.RedisCapManager.check_and_increment_total(
        offer_id=902,
        limit=30,
        publisher_id=34,
        initial_value=0,
        reservation_id="recreated-cap-request",
    )

    assert allowed is True
    assert redis.value == 18
    assert redis.calls[0][2] == redis_counter.get_total_cap_key(902, 34)
    assert redis.calls[0][5] == "0"
    assert redis.calls[0][4] == 0  # Total key 必须保持永久有效。
