"""Offer 状态校验必须 fail-closed，避免数据库故障时绕过准入控制。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.postback.pipeline import (
    PostbackPipelineContext,
    step_validate_offer_status,
)


def _context(db, association=None):
    return PostbackPipelineContext(
        platform="test",
        raw_data={},
        db=db,
        click_association=association,
    )


class _Result:
    def __init__(self, row):
        self.row = row

    def one_or_none(self):
        return self.row


@pytest.mark.asyncio
async def test_active_offer_is_allowed_and_database_state_overrides_cached_object():
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result((True, "Active"))))
    # 模拟关联器携带了已经过期的 ORM 对象；校验必须重新读取数据库。
    stale_offer = SimpleNamespace(is_active=False, status="Paused")
    ctx = _context(db, {"offer_id": 101, "offer": stale_offer})

    assert await step_validate_offer_status(ctx) is True
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        (False, "Active"),
        (True, "Paused"),
        (False, "Paused"),
    ],
)
async def test_inactive_offer_is_rejected(row):
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(row)))
    ctx = _context(db, {"offer_id": 102})

    assert await step_validate_offer_status(ctx) is False


@pytest.mark.asyncio
async def test_missing_offer_is_rejected():
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(None)))
    ctx = _context(db, {"offer_id": 103})

    assert await step_validate_offer_status(ctx) is False


@pytest.mark.asyncio
async def test_database_error_propagates_instead_of_fail_open():
    db_error = RuntimeError("database unavailable")
    db = SimpleNamespace(execute=AsyncMock(side_effect=db_error))
    ctx = _context(db, {"offer_id": 104})

    with pytest.raises(RuntimeError, match="database unavailable"):
        await step_validate_offer_status(ctx)


@pytest.mark.asyncio
async def test_direct_postback_without_offer_id_remains_allowed_without_query():
    db = SimpleNamespace(execute=AsyncMock())
    ctx = _context(db, {"click_id": "direct-postback"})

    assert await step_validate_offer_status(ctx) is True
    db.execute.assert_not_awaited()
