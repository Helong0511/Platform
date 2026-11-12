"""真实 Redis 隔离集成测试：验证短链接计数 Lua 脚本的原子行为。

仅在 CI 临时 Redis service 或显式隔离测试 Redis 中运行；
没有 REDIS_INTEGRATION_URL 时自动跳过，绝不读取应用生产配置。
"""
from __future__ import annotations

import ipaddress
import os
import uuid
from urllib.parse import urlsplit

import pytest
from redis.asyncio import Redis

from app.core import short_link_click_counter as counter
from app.core.cap.redis_counter import RedisCapManager
from app.core.infrastructure.cache_advanced import DistributedLock


REDIS_URL = os.getenv("REDIS_INTEGRATION_URL")


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip()).is_loopback
    except ValueError:
        return False


def _is_isolated_redis_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme in {"redis", "rediss"}
            and _is_loopback_host(parsed.hostname)
            and parsed.port in (None, 6379)
            and parsed.path.strip("/") == "14"
        )
    except ValueError:
        return False


_SAFE_REDIS_TARGET = (
    os.getenv("UNIT_TEST") == "1"
    and os.getenv("GITHUB_ACTIONS") == "true"
    and os.getenv("REDIS_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS") == "1"
    and _is_isolated_redis_url(REDIS_URL)
)

# 这些测试会向 Redis 写入并删除 key；禁止因环境变量误配置而连接远程/生产 Redis。
if os.getenv("UNIT_TEST") == "1" and (REDIS_URL or os.getenv("GITHUB_ACTIONS") == "true") and not _SAFE_REDIS_TARGET:
    raise RuntimeError(
        "拒绝执行 Redis 集成测试：必须使用 loopback Redis DB14，"
        "并显式设置 REDIS_INTEGRATION_ALLOW_DESTRUCTIVE_TESTS=1"
    )

pytestmark = pytest.mark.skipif(
    not _SAFE_REDIS_TARGET,
    reason="仅在 GitHub Actions 临时 Redis DB14 服务中运行",
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("redis://127.0.0.1:6379/14", True),
        ("redis://[::1]:6379/14", True),
        ("redis://localhost:6379/14", True),
        ("redis://127.0.0.1:6379/0", False),
        ("redis://192.0.2.10:6379/14", False),
        ("redis://redis.internal:6379/14", False),
        ("http://127.0.0.1:6379/14", False),
        (None, False),
    ],
)
def test_redis_integration_guard_requires_loopback_db14(url, expected):
    assert _is_isolated_redis_url(url) is expected


@pytest.mark.asyncio
async def test_real_redis_claim_pending_batch_and_decrement_acknowledged_counter():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    suffix = uuid.uuid4().hex
    active_key = f"ci:short-link:active:{suffix}"
    pending_key = f"ci:short-link:pending:{suffix}"
    counter_key = f"ci:short-link:counter:{suffix}"

    try:
        assert await redis.ping() is True

        # 活跃计数转 pending 必须由单条 Lua 脚本原子完成。
        await redis.set(active_key, 12)
        claimed = await redis.eval(
            counter._CLAIM_COUNTER_BATCH_LUA,
            2,
            active_key,
            pending_key,
        )
        assert claimed == 12
        assert await redis.get(active_key) is None
        assert await redis.get(pending_key) == "12"

        # pending 已存在时禁止覆盖；活跃计数必须保留，等待后续批次。
        await redis.set(active_key, 3)
        duplicate_claim = await redis.eval(
            counter._CLAIM_COUNTER_BATCH_LUA,
            2,
            active_key,
            pending_key,
        )
        assert duplicate_claim == -1
        assert await redis.get(active_key) == "3"
        assert await redis.get(pending_key) == "12"

        # 只有在 DB 入账成功后才调用的扣减脚本，按快照精确扣减。
        await redis.set(counter_key, 12)
        first_ack = await redis.eval(
            counter._DECREMENT_COUNTER_LUA,
            1,
            counter_key,
            5,
        )
        assert first_ack == 1
        assert await redis.get(counter_key) == "7"

        final_ack = await redis.eval(
            counter._DECREMENT_COUNTER_LUA,
            1,
            counter_key,
            7,
        )
        assert final_ack == 1
        assert await redis.get(counter_key) is None
    finally:
        await redis.delete(active_key, pending_key, counter_key)
        await redis.aclose()


@pytest.mark.asyncio
async def test_real_redis_distributed_lock_release_is_atomic_and_owner_scoped():
    """旧锁释放不能删除同 key 上由新请求持有的锁。"""
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    key = f"ci:cache:lock:{uuid.uuid4().hex}"
    old_owner = "old-owner-token"
    new_owner = "new-owner-token"

    try:
        assert await redis.set(key, old_owner, nx=True, ex=30) is True
        # 模拟旧锁过期后另一个请求重新获取同一 key。
        await redis.set(key, new_owner, ex=30)

        old_release = await redis.eval(
            DistributedLock._RELEASE_LUA,
            1,
            key,
            old_owner,
        )
        assert old_release == 0
        assert await redis.get(key) == new_owner

        new_release = await redis.eval(
            DistributedLock._RELEASE_LUA,
            1,
            key,
            new_owner,
        )
        assert new_release == 1
        assert await redis.get(key) is None
    finally:
        await redis.delete(key)
        await redis.aclose()



@pytest.mark.asyncio
async def test_real_redis_cap_rollback_preserves_token_when_counter_is_zero():
    """异常归零的计数器不得让回滚脚本静默删除 reservation 证据。"""
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    suffix = uuid.uuid4().hex
    counter_key = f"ci:cap:counter:{suffix}"
    token_key = f"ci:cap:reservation:{suffix}"

    try:
        assert await redis.ping() is True
        await redis.set(counter_key, 0)
        await redis.set(token_key, "1")

        result = await redis.eval(
            RedisCapManager._ROLLBACK_RESERVATION_LUA,
            2,
            counter_key,
            token_key,
        )

        assert result == -2
        assert await redis.get(counter_key) == "0"
        assert await redis.get(token_key) == "1"

        # 正常正数计数器仍然只扣减一次，并在同一 Lua 中删除 token。
        await redis.set(counter_key, 2)
        normal_result = await redis.eval(
            RedisCapManager._ROLLBACK_RESERVATION_LUA,
            2,
            counter_key,
            token_key,
        )
        assert normal_result == 1
        assert await redis.get(counter_key) == "1"
        assert await redis.get(token_key) is None
    finally:
        await redis.delete(counter_key, token_key)
        await redis.aclose()



@pytest.mark.asyncio
async def test_real_redis_cap_reservation_token_lifetime_and_corrupt_counter_fail_closed():
    """验证账本 token 无固定 TTL、稳定 token 幂等，以及损坏计数值 fail-closed。"""
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    suffix = uuid.uuid4().hex
    daily_key = f"ci:cap:daily:{suffix}"
    daily_token = f"{daily_key}:reservation:stable-token"
    total_key = f"ci:cap:total:{suffix}"
    total_token = f"{total_key}:reservation:stable-token"
    corrupt_key = f"ci:cap:corrupt:{suffix}"
    corrupt_token = f"{corrupt_key}:reservation:stable-token"
    fraction_key = f"ci:cap:fraction:{suffix}"
    fraction_token = f"{fraction_key}:reservation:stable-token"

    try:
        assert await redis.ping() is True

        first = await redis.eval(
            RedisCapManager._RESERVE_LUA, 2,
            daily_key, daily_token, 48 * 3600, 3, 10, 0,
        )
        assert first == 4
        assert await redis.ttl(daily_key) > 0
        assert await redis.ttl(daily_token) == -1

        # 相同 token 重试只返回原计数，不重复 INCR。
        retry = await redis.eval(
            RedisCapManager._RESERVE_LUA, 2,
            daily_key, daily_token, 48 * 3600, 3, 10, 0,
        )
        assert retry == 4
        assert await redis.get(daily_key) == "4"
        assert await redis.ttl(daily_token) == -1

        # 已有 token 的幂等重试也必须拒绝损坏的非整数计数，且保留 token 证据。
        await redis.set(daily_key, "4.5")
        corrupt_retry = await redis.eval(
            RedisCapManager._RESERVE_LUA, 2,
            daily_key, daily_token, 48 * 3600, 3, 10, 0,
        )
        assert corrupt_retry == -2
        assert await redis.get(daily_key) == "4.5"
        assert await redis.get(daily_token) == "1"
        await redis.set(daily_key, 4)

        # Total counter 和活动 token 都必须持久化，直到账本终态清理 token。
        total = await redis.eval(
            RedisCapManager._RESERVE_LUA, 2,
            total_key, total_token, 0, 7, 10, 0,
        )
        assert total == 8
        assert await redis.ttl(total_key) == -1
        assert await redis.ttl(total_token) == -1

        # 已存在但非整数的 Redis counter 不能被 DB 初值覆盖。
        await redis.set(corrupt_key, "not-an-integer")
        corrupt_result = await redis.eval(
            RedisCapManager._RESERVE_LUA, 2,
            corrupt_key, corrupt_token, 48 * 3600, 0, 10, 0,
        )
        assert corrupt_result == -2
        assert await redis.get(corrupt_key) == "not-an-integer"
        assert await redis.get(corrupt_token) is None

        invalid_baseline = await redis.eval(
            RedisCapManager._RESERVE_LUA, 2,
            f"{corrupt_key}:baseline", f"{corrupt_token}:baseline",
            48 * 3600, "not-an-integer", 10, 0,
        )
        invalid_limit = await redis.eval(
            RedisCapManager._RESERVE_LUA, 2,
            f"{corrupt_key}:limit", f"{corrupt_token}:limit",
            48 * 3600, 0, 0, 0,
        )
        assert invalid_baseline == -2
        assert invalid_limit == -2

        # 回滚遇到非整数计数时也必须保留 token，不能先删证据再让 DECR 抛错。
        await redis.set(fraction_key, "1.5")
        await redis.set(fraction_token, "1")
        fraction_rollback = await redis.eval(
            RedisCapManager._ROLLBACK_RESERVATION_LUA, 2,
            fraction_key, fraction_token,
        )
        assert fraction_rollback == -2
        assert await redis.get(fraction_key) == "1.5"
        assert await redis.get(fraction_token) == "1"

        # 正常 rollback 只撤销一次，并清理 token；重复 rollback 不会误减。
        rollback = await redis.eval(
            RedisCapManager._ROLLBACK_RESERVATION_LUA, 2,
            daily_key, daily_token,
        )
        assert rollback == 3
        duplicate_rollback = await redis.eval(
            RedisCapManager._ROLLBACK_RESERVATION_LUA, 2,
            daily_key, daily_token,
        )
        assert duplicate_rollback == -3  # token 缺失必须进入对账，不能假报成功
        assert await redis.get(daily_key) == "3"
    finally:
        await redis.delete(
            daily_key, daily_token, total_key, total_token,
            corrupt_key, corrupt_token, fraction_key, fraction_token,
            f"{corrupt_key}:baseline", f"{corrupt_token}:baseline",
            f"{corrupt_key}:limit", f"{corrupt_token}:limit",
        )
        await redis.aclose()
