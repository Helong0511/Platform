"""事件身份约束扣量策略的回归测试。"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.deduction.deduction_manager import DeductionManager


def _config(strategy="random"):
    return SimpleNamespace(
        enable_volume_deduction=True,
        enable_amount_deduction=False,
        volume_deduction_ratio=Decimal("0.25"),
        amount_deduction_ratio=Decimal("0"),
        deduction_strategy=strategy,
    )


def test_event_decision_key_is_bound_to_platform_conversion_and_event():
    key = DeductionManager._build_event_decision_key({
        "platform": "BFT",
        "conversion_id": "conversion-1",
        "event_name": "purchase",
    })
    same = DeductionManager._build_event_decision_key({
        "platform": "bft",
        "conversion_id": "conversion-1",
        "event_name": "purchase",
    })
    different_conversion = DeductionManager._build_event_decision_key({
        "platform": "bft",
        "conversion_id": "conversion-2",
        "event_name": "purchase",
    })
    different_event = DeductionManager._build_event_decision_key({
        "platform": "bft",
        "conversion_id": "conversion-1",
        "event_name": "refund",
    })

    assert key is not None
    assert key == same
    assert key != different_conversion
    assert key != different_event


@pytest.mark.parametrize(
    "identity",
    [
        None,
        {},
        {"platform": "bft", "conversion_id": "", "event_name": "purchase"},
        {"platform": "bft", "conversion_id": "x" * 256, "event_name": "purchase"},
        {"platform": "bft", "conversion_id": "conversion-1", "event_name": "x" * 101},
    ],
)
def test_invalid_or_unverified_event_identity_has_no_decision_key(identity):
    assert DeductionManager._build_event_decision_key(identity) is None


@pytest.mark.asyncio
async def test_click_id_alone_never_authorizes_volume_deduction():
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        side_effect=AssertionError("unverified identity must not read decision counters")
    )

    result = await manager.apply_deduction(
        {"original_payout": "10.00"},
        _config(),
        click_id="click-shared-by-multiple-conversions",
        offer_id=9,
    )

    assert result.should_deduct_volume is False
    assert result.final_volume == 1
    manager._get_stats_for_decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordered_strategies_are_paused_until_mysql_ledger_is_authoritative():
    manager = DeductionManager(db=object())
    manager._get_stats_for_decision = AsyncMock(
        side_effect=AssertionError("ordered strategy must not use Redis sequence")
    )

    result = await manager.apply_deduction(
        {"original_payout": "10.00"},
        _config(strategy="proportional"),
        event_identity={
            "platform": "bft",
            "conversion_id": "conversion-ordered-1",
            "event_name": "purchase",
        },
    )

    assert result.should_deduct_volume is False
    assert result.final_volume == 1
    manager._get_stats_for_decision.assert_not_awaited()


@pytest.mark.asyncio
async def test_hash_strategy_uses_event_key_instead_of_click_id():
    manager = DeductionManager(db=object())
    identity = {
        "platform": "bft",
        "conversion_id": "conversion-hash-1",
        "event_name": "purchase",
    }
    captured = {}
    manager._get_stats_for_decision = AsyncMock(
        return_value=__import__("app.core.deduction.deduction_manager", fromlist=["ConversionStats"]).ConversionStats(total=0, deducted=0, processed=0)
    )
    manager.should_deduct_volume = lambda config, stats, decision_key="": captured.setdefault("key", decision_key) or True
    manager._incr_decision_deducted = AsyncMock(return_value=True)

    result = await manager.apply_deduction(
        {"original_payout": "10.00"},
        _config(strategy="hash"),
        click_id="attribution-click-not-event-id",
        offer_id=7,
        event_identity=identity,
    )

    assert captured["key"] == DeductionManager._build_event_decision_key(identity)
    assert result.should_deduct_volume is True
    manager._incr_decision_deducted.assert_awaited_once()
