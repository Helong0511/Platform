"""Redis unavailable must not be reported as a successful Cap sync."""

import pytest

from app.core.cap import cap_sync


@pytest.mark.asyncio
async def test_sync_all_active_caps_raises_when_redis_is_unavailable(monkeypatch):
    async def unavailable_redis():
        return None

    monkeypatch.setattr(cap_sync, "get_redis_client", unavailable_redis)

    with pytest.raises(RuntimeError, match="Redis 不可用"):
        await cap_sync.CapSynchronizer(db=None).sync_all_active_caps()
