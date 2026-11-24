"""CPL 扣量统计窗口和 Redis 冷启动基线回归测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.deduction import deduction_manager as deduction_manager_module
from app.core.deduction.deduction_manager import ConversionStats, DeductionManager


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


@pytest.mark.asyncio
async def test_recent_stats_counts_saved_conversions_and_only_unpersisted_volume_deductions(monkeypatch):
    monkeypatch.setattr(
        deduction_manager_module,
        "get_cached",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(deduction_manager_module, "set_cached", AsyncMock())

    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _ScalarResult(120),  # 已入库的正常/扣金额转化
                _ScalarResult(8),    # 未入库的扣量命中
                _ScalarResult(3),    # 已入库且明确标记扣量的转化
            ]
        )
    )

    stats = await DeductionManager(db).get_recent_stats(
        advertiser_id=12,
        offer_id=34,
        publisher_id=56,
        hours=24,
    )

    assert stats == ConversionStats(total=128, deducted=11, processed=128)
    assert db.execute.await_count == 3

    conversion_sql = str(db.execute.await_args_list[0].args[0])
    volume_log_sql = str(db.execute.await_args_list[1].args[0])
    assert "postback_conversions" in conversion_sql
    assert "conversion_deduction_logs" in volume_log_sql
    assert "deducted_volume" in volume_log_sql
    assert "conversion_id IS NULL" in volume_log_sql


@pytest.mark.asyncio
async def test_decision_stats_recover_processed_and_deducted_from_database_baseline(monkeypatch):
    manager = DeductionManager(db=SimpleNamespace())
    manager.get_recent_stats = AsyncMock(
        return_value=ConversionStats(total=31, deducted=7, processed=31)
    )
    redis = SimpleNamespace(eval=AsyncMock(return_value=[32, 2]))
    monkeypatch.setattr(
        deduction_manager_module,
        "get_redis_client",
        AsyncMock(return_value=redis),
    )

    stats = await manager._get_stats_for_decision(
        advertiser_id=12,
        offer_id=34,
        publisher_id=56,
        hours=24,
    )

    assert stats == ConversionStats(total=32, deducted=7, processed=32)
    args = redis.eval.await_args.args
    assert args[4] == 24 * 60 * 60
    assert args[5] == 7
    assert args[6] == 31
    assert "current_deducted < init_deducted" in args[0]


def test_decision_counter_ttl_matches_requested_statistics_window():
    assert DeductionManager._decision_ttl(24) == 86400
    assert DeductionManager._decision_ttl(6) == 21600
