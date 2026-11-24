"""CPL 扣量统计口径与应用时区回归测试。"""
from datetime import datetime
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
    app_now = datetime(2026, 11, 24, 12, 0, 0)
    monkeypatch.setattr(deduction_manager_module, "get_app_now_naive", lambda: app_now)

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

    conversion_stmt = db.execute.await_args_list[0].args[0]
    volume_log_stmt = db.execute.await_args_list[1].args[0]
    conversion_sql = str(conversion_stmt)
    volume_log_sql = str(volume_log_stmt)
    assert "postback_conversions" in conversion_sql
    assert "conversion_deduction_logs" in volume_log_sql
    # 两类数据均使用 [start_time, end_time) 半开区间，防止相邻窗口重复计算边界事件。
    assert " < " in conversion_sql
    assert " <= " not in conversion_sql
    assert " < " in volume_log_sql
    assert " <= " not in volume_log_sql
    assert "deducted_volume" in volume_log_sql
    assert "conversion_id IS NULL" in volume_log_sql

    # SQL 时间参数必须来自应用配置时区，而不是操作系统本机时区。
    conversion_params = conversion_stmt.compile().params
    assert app_now in conversion_params.values()
    assert datetime(2026, 11, 23, 12, 0, 0) in conversion_params.values()



@pytest.mark.asyncio
async def test_strict_recent_stats_bypasses_stale_cache_and_does_not_refresh_it(monkeypatch):
    stale_cache = AsyncMock(
        return_value={"total": 999, "deducted": 999, "processed": 999}
    )
    cache_write = AsyncMock()
    monkeypatch.setattr(deduction_manager_module, "get_cached", stale_cache)
    monkeypatch.setattr(deduction_manager_module, "set_cached", cache_write)
    monkeypatch.setattr(
        deduction_manager_module,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 24, 12, 0, 0),
    )

    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _ScalarResult(20),
                _ScalarResult(2),
                _ScalarResult(1),
            ]
        )
    )

    stats = await DeductionManager(db).get_recent_stats(
        advertiser_id=12,
        offer_id=34,
        publisher_id=56,
        hours=24,
        strict=True,
    )

    assert stats == ConversionStats(total=22, deducted=3, processed=22)
    stale_cache.assert_not_awaited()
    cache_write.assert_not_awaited()
    assert db.execute.await_count == 3
