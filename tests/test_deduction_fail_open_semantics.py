"""CPL 扣量使用 MySQL 权威统计的 fail-open / fail-close 回归测试。"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.deduction import deduction_manager as deduction_manager_module
from app.core.deduction.deduction_manager import ConversionStats, DeductionManager


def _config(*, volume=True, amount=False, ratio="1.0", strategy="random"):
    return SimpleNamespace(
        enable_volume_deduction=volume,
        enable_amount_deduction=amount,
        volume_deduction_ratio=Decimal(ratio) if volume else Decimal("0"),
        amount_deduction_ratio=Decimal("0.1") if amount else Decimal("0"),
        deduction_strategy=strategy,
    )


_EVENT = {
    "platform": "test",
    "conversion_id": "stable-event-001",
    "event_name": "purchase",
}


@pytest.mark.asyncio
async def test_amount_only_deduction_does_not_read_volume_stats():
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        side_effect=AssertionError("amount-only must not read volume stats")
    )

    result = await manager.apply_deduction(
        {"original_payout": "10.00"},
        _config(volume=False, amount=True),
    )

    assert result.should_deduct_amount is True
    assert result.should_deduct_volume is False
    assert result.final_amount == Decimal("9.000")
    manager._get_stats_for_decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_fail_open_skips_volume_when_authoritative_mysql_stats_fail(monkeypatch):
    monkeypatch.setattr(
        deduction_manager_module.settings,
        "DEDUCTION_FAIL_OPEN",
        True,
    )
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        side_effect=RuntimeError("database unavailable")
    )

    result = await manager.apply_deduction(
        {"original_payout": "10.00"},
        _config(volume=True, amount=True),
        event_identity=_EVENT,
    )

    assert result.should_deduct_volume is False
    assert result.should_deduct_amount is True
    assert result.final_volume == 1
    assert result.final_amount == Decimal("9.000")


@pytest.mark.asyncio
async def test_fail_close_rejects_volume_decision_when_mysql_stats_fail(monkeypatch):
    monkeypatch.setattr(
        deduction_manager_module.settings,
        "DEDUCTION_FAIL_OPEN",
        False,
    )
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        side_effect=RuntimeError("database unavailable")
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await manager.apply_deduction(
            {"original_payout": "10.00"},
            _config(volume=True, amount=False),
            event_identity=_EVENT,
        )


@pytest.mark.asyncio
async def test_volume_decision_uses_mysql_stats_without_redis(monkeypatch):
    redis_client = AsyncMock(
        side_effect=AssertionError("Redis must not participate in financial decisions")
    )
    monkeypatch.setattr(
        deduction_manager_module,
        "get_redis_client",
        redis_client,
    )
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        return_value=ConversionStats(total=0, deducted=0, processed=0)
    )
    manager.should_deduct_volume = lambda config, stats, decision_key="": True

    result = await manager.apply_deduction(
        {"original_payout": "10.00"},
        _config(volume=True, ratio="1.0", strategy="hash"),
        event_identity=_EVENT,
    )

    assert result.should_deduct_volume is True
    assert result.deducted_volume == 1
    assert result.final_volume == 0
    redis_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_sequential_strategy_uses_scope_locked_mysql_processed_count():
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        return_value=ConversionStats(total=1, deducted=0, processed=1)
    )

    result = await manager.apply_deduction(
        {"original_payout": "10.00"},
        _config(volume=True, ratio="0.5", strategy="proportional"),
        event_identity=_EVENT,
    )

    # 第 2 个事件命中 50% 间隔策略；额度按 total + 当前事件计算。
    assert result.should_deduct_volume is True
    assert result.deducted_volume == 1


@pytest.mark.asyncio
async def test_mysql_window_quota_prevents_deduction_above_ratio():
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        return_value=ConversionStats(total=10, deducted=1, processed=10)
    )
    manager.should_deduct_volume = lambda config, stats, decision_key="": True

    result = await manager.apply_deduction(
        {"original_payout": "10.00"},
        _config(volume=True, ratio="0.1", strategy="hash"),
        event_identity=_EVENT,
    )

    # 当前事件将成为窗口内第 11 个事件，10% 上限仍为 1 条。
    assert result.should_deduct_volume is False
    assert result.deducted_volume == 0


@pytest.mark.asyncio
async def test_strict_decision_stats_are_mysql_only_and_bypass_cache(monkeypatch):
    class ScalarResult:
        def __init__(self, value):
            self.value = value

        def scalar_one(self):
            return self.value

    monkeypatch.setattr(
        deduction_manager_module,
        "get_cached",
        AsyncMock(side_effect=AssertionError("strict stats must bypass cache")),
    )
    monkeypatch.setattr(
        deduction_manager_module,
        "set_cached",
        AsyncMock(side_effect=AssertionError("strict stats must not write cache")),
    )
    redis_client = AsyncMock(
        side_effect=AssertionError("strict stats must not access Redis")
    )
    monkeypatch.setattr(
        deduction_manager_module,
        "get_redis_client",
        redis_client,
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarResult(20),
                ScalarResult(2),
                ScalarResult(1),
            ]
        )
    )

    stats = await DeductionManager(db)._get_stats_for_decision(
        advertiser_id=12,
        hours=24,
    )

    assert stats == ConversionStats(total=22, deducted=3, processed=22)
    assert db.execute.await_count == 3
    redis_client.assert_not_awaited()
