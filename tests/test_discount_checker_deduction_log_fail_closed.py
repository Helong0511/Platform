"""扣量审计日志是财务凭证，持久化失败不得被 Redis fail-open 吞掉。"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.postback.checks import discount_checker as discount_checker_module
from app.core.postback.checks.discount_checker import DiscountChecker
from app.core.postback.errors import DeductionProcessingError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "deduction_result",
    [
        {
            "should_deduct_volume": True,
            "should_deduct_amount": False,
            "final_amount": Decimal("0"),
        },
        {
            "should_deduct_volume": False,
            "should_deduct_amount": True,
            "final_amount": Decimal("9.00"),
        },
    ],
)
async def test_deduction_log_persistence_failure_is_fail_closed_even_when_redis_fail_open(
    monkeypatch,
    deduction_result,
):
    monkeypatch.setattr(
        discount_checker_module.settings,
        "DEDUCTION_FAIL_OPEN",
        True,
    )
    monkeypatch.setattr(
        discount_checker_module,
        "find_deduction_config",
        AsyncMock(return_value=SimpleNamespace(
            id=7, advertiser_id=12, offer_id=None, publisher_id=None
        )),
    )
    monkeypatch.setattr(
        discount_checker_module,
        "apply_deduction",
        AsyncMock(return_value=deduction_result),
    )
    monkeypatch.setattr(
        discount_checker_module,
        "log_deduction",
        AsyncMock(side_effect=RuntimeError("database log write failed")),
    )

    with pytest.raises(DeductionProcessingError, match="记录扣"):
        await DiscountChecker.calculate(
            original_payout=Decimal("10.00"),
            offer_id=None,
            publisher_id=None,
            product_id=None,
            client_id=None,
            advertiser_id=12,
            click_id="click-1",
            db=object(),
        )

    discount_checker_module.log_deduction.assert_awaited_once()
