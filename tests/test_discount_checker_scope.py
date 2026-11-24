"""验证扣量统计严格使用最终命中配置的唯一 scope。"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.postback.checks import discount_checker as module
from app.core.postback.checks.discount_checker import DiscountChecker
from app.core.postback.errors import DeductionProcessingError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config_scope", "expected_scope"),
    [
        ({"advertiser_id": 11, "offer_id": None, "publisher_id": None},
         {"advertiser_id": 11, "offer_id": None, "publisher_id": None}),
        ({"advertiser_id": None, "offer_id": 22, "publisher_id": None},
         {"advertiser_id": None, "offer_id": 22, "publisher_id": None}),
        ({"advertiser_id": None, "offer_id": None, "publisher_id": 33},
         {"advertiser_id": None, "offer_id": None, "publisher_id": 33}),
    ],
)
async def test_apply_deduction_receives_only_final_config_scope(
    monkeypatch, config_scope, expected_scope
):
    config = SimpleNamespace(id=7, **config_scope)
    apply_mock = AsyncMock(return_value={
        "should_deduct_volume": False,
        "should_deduct_amount": False,
        "final_amount": Decimal("10.00"),
    })
    monkeypatch.setattr(module, "calculate_discount", AsyncMock(return_value=(Decimal("10.00"), Decimal("0"), None)))
    monkeypatch.setattr(module, "find_deduction_config", AsyncMock(return_value=config))
    monkeypatch.setattr(module, "apply_deduction", apply_mock)

    await DiscountChecker.calculate(
        original_payout=Decimal("10.00"),
        offer_id=22,
        publisher_id=33,
        product_id=None,
        client_id=None,
        advertiser_id=11,
        click_id="stable-click",
        db=object(),
        event_identity={"platform": "bft", "conversion_id": "event-1", "event_name": "purchase"},
    )

    assert apply_mock.await_args.kwargs["event_identity"] == {
        "platform": "bft", "conversion_id": "event-1", "event_name": "purchase"
    }
    assert apply_mock.await_args.kwargs["advertiser_id"] == expected_scope["advertiser_id"]
    assert apply_mock.await_args.kwargs["offer_id"] == expected_scope["offer_id"]
    assert apply_mock.await_args.kwargs["publisher_id"] == expected_scope["publisher_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config_scope",
    [
        {"advertiser_id": None, "offer_id": None, "publisher_id": None},
        {"advertiser_id": 11, "offer_id": 22, "publisher_id": None},
        {"advertiser_id": 0, "offer_id": None, "publisher_id": None},
    ],
)
async def test_invalid_multi_or_missing_config_scope_fails_closed(monkeypatch, config_scope):
    monkeypatch.setattr(module.settings, "DEDUCTION_FAIL_OPEN", True)
    config = SimpleNamespace(id=7, **config_scope)
    apply_mock = AsyncMock()
    monkeypatch.setattr(module, "find_deduction_config", AsyncMock(return_value=config))
    monkeypatch.setattr(module, "apply_deduction", apply_mock)

    with pytest.raises(DeductionProcessingError, match="配置层级数据异常"):
        await DiscountChecker.calculate(
            original_payout=Decimal("10.00"),
            offer_id=22,
            publisher_id=33,
            product_id=None,
            client_id=None,
            advertiser_id=11,
            click_id="stable-click",
            db=object(),
        )
    apply_mock.assert_not_awaited()
