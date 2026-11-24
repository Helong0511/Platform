"""CPL Redis 故障时的 fail-open / fail-close 回归测试。"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.deduction import deduction_manager as deduction_manager_module
from app.core.deduction.deduction_manager import ConversionStats, DeductionManager


def _config(*, volume=True, amount=False):
    return SimpleNamespace(
        enable_volume_deduction=volume,
        enable_amount_deduction=amount,
        volume_deduction_ratio=Decimal("1.0") if volume else Decimal("0"),
        amount_deduction_ratio=Decimal("0.1") if amount else Decimal("0"),
        deduction_strategy="proportional",
    )


@pytest.mark.asyncio
async def test_amount_only_deduction_does_not_require_redis(monkeypatch):
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        side_effect=AssertionError("amount-only must not read Redis")
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
async def test_fail_open_skips_unsafe_volume_but_still_applies_amount(monkeypatch):
    monkeypatch.setattr(
        deduction_manager_module.settings,
        "DEDUCTION_FAIL_OPEN",
        True,
    )
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        side_effect=RuntimeError("Redis unavailable")
    )
    manager._incr_decision_deducted = AsyncMock(
        side_effect=AssertionError("must not increment without a decision")
    )

    result = await manager.apply_deduction(
        {"original_payout": "10.00"},
        _config(volume=True, amount=True),
    )

    assert result.should_deduct_volume is False
    assert result.should_deduct_amount is True
    assert result.final_volume == 1
    assert result.final_amount == Decimal("9.000")
    manager._incr_decision_deducted.assert_not_awaited()


@pytest.mark.asyncio
async def test_fail_close_rejects_volume_decision_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        deduction_manager_module.settings,
        "DEDUCTION_FAIL_OPEN",
        False,
    )
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        side_effect=RuntimeError("Redis unavailable")
    )

    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await manager.apply_deduction(
            {"original_payout": "10.00"},
            _config(volume=True, amount=False),
        )


@pytest.mark.asyncio
async def test_increment_counter_returns_false_when_fail_open_has_no_redis(monkeypatch):
    monkeypatch.setattr(
        deduction_manager_module.settings,
        "DEDUCTION_FAIL_OPEN",
        True,
    )
    monkeypatch.setattr(
        deduction_manager_module,
        "get_redis_client",
        AsyncMock(return_value=None),
    )

    manager = DeductionManager(db=object())
    incremented = await manager._incr_decision_deducted(
        advertiser_id=1,
        offer_id=2,
        publisher_id=3,
        hours=24,
    )

    assert incremented is False


@pytest.mark.asyncio
async def test_strict_decision_stats_do_not_silently_return_zero_on_db_failure(monkeypatch):
    monkeypatch.setattr(
        deduction_manager_module.settings,
        "DEDUCTION_FAIL_OPEN",
        True,
    )
    monkeypatch.setattr(
        deduction_manager_module,
        "get_cached",
        AsyncMock(return_value=None),
    )
    db = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("database down")))

    with pytest.raises(RuntimeError, match="database down"):
        await DeductionManager(db).get_recent_stats(strict=True)

    # 非决策用途仍保留既有 fail-open 返回行为。
    stats = await DeductionManager(db).get_recent_stats(strict=False)
    assert stats == ConversionStats()
