"""扣量 scope 互斥锁的事务边界与排序测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.deduction.deduction_manager import DeductionManager
from app.services.cpl.deduction import helpers as deduction_helpers
from app.services.cpl.deduction.helpers import lock_deduction_scopes


class _LockResult:
    def scalar_one_or_none(self):
        return 1


@pytest.mark.asyncio
async def test_scope_locks_are_deduplicated_and_sorted_without_commit():
    db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="mysql")),
        execute=AsyncMock(return_value=_LockResult()),
        commit=AsyncMock(),
    )

    await lock_deduction_scopes(
        db,
        [
            ("publisher", 9),
            ("offer", 7),
            ("advertiser", 3),
            ("offer", 7),
        ],
    )

    assert db.execute.await_count == 6
    assert db.commit.await_count == 0
    insert_params = [
        call.args[1]
        for call in db.execute.await_args_list
        if "INSERT INTO conversion_deduction_scope_locks" in str(call.args[0])
    ]
    assert insert_params == [
        {"scope_type": "advertiser", "scope_id": 3},
        {"scope_type": "offer", "scope_id": 7},
        {"scope_type": "publisher", "scope_id": 9},
    ]


@pytest.mark.asyncio
async def test_scope_lock_rejects_unsupported_database_dialect():
    db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="不支持当前数据库方言"):
        await lock_deduction_scopes(db, [("offer", 1)])

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_scope_lock_rejects_non_positive_or_boolean_ids():
    db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="mysql")),
        execute=AsyncMock(),
    )

    for invalid_id in (0, -1, True, "1"):
        with pytest.raises(Exception):
            await lock_deduction_scopes(db, [("offer", invalid_id)])

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_postback_locks_all_candidate_scopes_before_current_reads(monkeypatch):
    calls = []
    async def lock_scopes(db, scopes):
        calls.append(("lock", scopes))

    monkeypatch.setattr(
        deduction_helpers,
        "lock_deduction_scopes",
        lock_scopes,
    )
    manager = DeductionManager(db=object())

    async def find_offer(offer_id):
        calls.append(("offer", offer_id))
        return "offer-config"

    manager._find_offer_config = find_offer
    manager._find_advertiser_config = AsyncMock()
    manager._find_publisher_config = AsyncMock()

    config = await manager.find_config(
        advertiser_id=2,
        offer_id=1,
        publisher_id=3,
    )

    assert config == "offer-config"
    assert calls[0] == (
        "lock",
        [("advertiser", 2), ("offer", 1), ("publisher", 3)],
    )
    assert calls[1] == ("offer", 1)
    manager._find_advertiser_config.assert_not_awaited()
    manager._find_publisher_config.assert_not_awaited()


def test_deduction_model_has_database_scope_uniqueness_guards():
    from app.models.deduction import ConversionDeductionConfig

    table = ConversionDeductionConfig.__table__
    unique_names = {
        constraint.name
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert {
        "uq_cpl_active_advertiser",
        "uq_cpl_active_offer",
        "uq_cpl_active_publisher",
    }.issubset(unique_names)
    assert any(
        constraint.name == "chk_cpl_deduction_exactly_one_scope"
        for constraint in table.constraints
    )
    assert {
        "active_advertiser_id",
        "active_offer_id",
        "active_publisher_id",
    }.issubset(table.columns.keys())


@pytest.mark.asyncio
async def test_postback_fails_closed_when_scope_lock_is_unavailable(monkeypatch):
    from app.core.config import settings
    from app.core.postback.checks import discount_checker
    from app.core.postback.errors import DeductionProcessingError
    from app.services.cpl.deduction.helpers import DeductionScopeLockError

    monkeypatch.setattr(settings, "DEDUCTION_FAIL_OPEN", True)
    monkeypatch.setattr(
        discount_checker,
        "find_deduction_config",
        AsyncMock(side_effect=DeductionScopeLockError("lock table unavailable")),
    )

    with pytest.raises(DeductionProcessingError, match="scope 锁获取失败"):
        await discount_checker.DiscountChecker.calculate(
            original_payout="10.00",
            offer_id=None,
            publisher_id=None,
            product_id=None,
            client_id=None,
            advertiser_id=None,
            click_id=None,
            db=object(),
        )


@pytest.mark.asyncio
async def test_scope_lock_rejects_unbound_session_as_domain_lock_error():
    from app.services.cpl.deduction.helpers import DeductionScopeLockError

    with pytest.raises(DeductionScopeLockError, match="不支持当前数据库方言"):
        await lock_deduction_scopes(object(), [("offer", 1)])
