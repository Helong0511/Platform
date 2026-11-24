"""扣量配置缓存键空间回归测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.deduction.deduction_cache import DeductionConfigCache
from app.core.infrastructure import cache_compat
from app.services.cpl.deduction import helpers as deduction_helpers


class _Cache:
    def __init__(self):
        self.get_keys = []
        self.set_keys = []
        self.patterns = []

    async def get(self, key):
        self.get_keys.append(key)
        return None

    async def set(self, key, value, ttl=None):
        self.set_keys.append(key)
        return True

    async def delete_pattern(self, pattern):
        self.patterns.append(pattern)
        return 1


class _Metrics:
    def record_hit(self, *args):
        pass

    def record_miss(self, *args):
        pass

    def record_error(self, *args):
        pass


@pytest.mark.asyncio
async def test_deduction_config_read_write_and_invalidation_share_query_namespace(monkeypatch):
    cache = _Cache()

    async def get_backend():
        return cache

    monkeypatch.setattr(cache_compat, "get_cache_backend", get_backend)
    monkeypatch.setattr(cache_compat, "get_metrics_collector", lambda: _Metrics())

    config = SimpleNamespace(
        id=9,
        offer_id=7,
        publisher_id=None,
        advertiser_id=None,
        volume_deduction_ratio=0.2,
        amount_deduction_ratio=0,
        priority=1,
        is_active=True,
        deduction_strategy="random",
        enable_volume_deduction=True,
        enable_amount_deduction=False,
        created_at=None,
        updated_at=None,
    )
    db = SimpleNamespace(scalar=AsyncMock(return_value=17))
    service = DeductionConfigCache(db=db)
    service._load_from_db = AsyncMock(return_value=config)

    await service.get_config("offer", 7)

    expected_key = "query_cache:cpl:deduction_config:offer:7:g17"
    assert cache.get_keys == [expected_key]
    assert cache.set_keys == [expected_key]
    # 读取与缓存回填必须复用同一数据库 Generation，不能在回填时重新取版本。
    db.scalar.assert_awaited_once()

    # 两条现有失效入口都必须命中与读写相同的 Redis 键空间。
    await service.invalidate("offer", 7)
    await deduction_helpers.invalidate_config_cache("offer", 7)

    expected_pattern = "query_cache:cpl:deduction_config:offer:7*"
    assert cache.patterns == [expected_pattern, expected_pattern]


@pytest.mark.asyncio
async def test_deduction_cache_reads_generation_once_for_all_priority_levels(monkeypatch):
    cache = _Cache()

    async def get_backend():
        return cache

    monkeypatch.setattr(cache_compat, "get_cache_backend", get_backend)
    monkeypatch.setattr(cache_compat, "get_metrics_collector", lambda: _Metrics())

    db = SimpleNamespace(scalar=AsyncMock(return_value=29))
    service = DeductionConfigCache(db=db)
    service._load_from_db = AsyncMock(return_value=None)

    await service.get_config("offer", 7)
    await service.get_config("advertiser", 3)
    await service.get_config("publisher", 11)

    db.scalar.assert_awaited_once()
    assert service._generation == 29
