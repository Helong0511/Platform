"""Redis Cap recovery must reconcile an existing stale key with the DB fallback count."""
import pytest

from app.core.cap import redis_counter


class _StatefulRedis:
    def __init__(self, initial_value):
        self.value = initial_value
        self.calls = []

    async def eval(self, script, numkeys, key, token_key, expire_seconds, db_count, limit):
        self.calls.append((script, numkeys, key, token_key, expire_seconds, db_count, limit))
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
    script, numkeys, key, token_key, _ttl, db_count, limit = redis.calls[0]
    assert numkeys == 2
    assert ":reservation:" in token_key
    assert key.startswith(f"cpl:cap:{key_kind}:901:")
    assert db_count == "7"
    assert limit == "20"
    assert "math.max(current, db_count)" in script
    assert "if not current then" in script
