"""Postback 重复检测与扣量逻辑单元测试。"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.postback.checks.discount_checker import DiscountChecker
from app.core.postback.validators.duplicate_checker import DuplicateChecker


@pytest.mark.asyncio
async def test_duplicate_checker_uses_platform_event_triplet():
    db = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = 99
    db.execute.return_value = scalar_result

    is_dup = await DuplicateChecker.is_duplicate(
        platform="test_platform",
        conversion_id="conv-1",
        event_name="install",
        db=db,
    )

    assert is_dup is True
    sql_text = str(db.execute.call_args[0][0])
    assert "platform" in sql_text.lower()
    assert "event_name" in sql_text.lower()


@pytest.mark.asyncio
async def test_discount_checker_volume_deduction_skips_save(monkeypatch):
    db = AsyncMock()

    async def fake_calculate_discount(*args, **kwargs):
        return 10.0, 0.0, None

    async def fake_find_config(*args, **kwargs):
        return MagicMock(id=1)

    async def fake_apply_deduction(*args, **kwargs):
        return {
            "should_deduct_volume": True,
            "should_deduct_amount": False,
            "final_amount": 0.0,
        }

    async def fake_log_deduction(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.core.postback.checks.discount_checker.calculate_discount",
        fake_calculate_discount,
    )
    monkeypatch.setattr(
        "app.core.postback.checks.discount_checker.find_deduction_config",
        fake_find_config,
    )
    monkeypatch.setattr(
        "app.core.postback.checks.discount_checker.apply_deduction",
        fake_apply_deduction,
    )
    monkeypatch.setattr(
        "app.core.postback.checks.discount_checker.log_deduction",
        fake_log_deduction,
    )

    final_payout, info, skip = await DiscountChecker.calculate(
        original_payout=10.0,
        offer_id=1,
        publisher_id=2,
        product_id=None,
        client_id=None,
        advertiser_id=3,
        click_id="clk-1",
        db=db,
    )

    assert skip is True
    assert final_payout == 0.0
    assert info["deduction_config"]["should_deduct_volume"] is True
