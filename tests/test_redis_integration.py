"""真实 Redis 隔离集成测试：验证短链接计数 Lua 脚本的原子行为。

仅在 CI 临时 Redis service 或显式隔离测试 Redis 中运行；
没有 REDIS_INTEGRATION_URL 时自动跳过，绝不读取应用生产配置。
"""
from __future__ import annotations

import os
import uuid

import pytest
from redis.asyncio import Redis

from app.core import short_link_click_counter as counter


REDIS_URL = os.getenv("REDIS_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not REDIS_URL,
    reason="仅在显式配置的隔离 Redis 集成环境中运行",
)


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
