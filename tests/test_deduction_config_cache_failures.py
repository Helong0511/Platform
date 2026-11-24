"""扣量配置缓存损坏与数据库故障边界回归测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.deduction import deduction_cache as cache_module
from app.core.deduction.deduction_cache import DeductionConfigCache


class _Scalars:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _Result:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return _Scalars(self.value)


@pytest.mark.asyncio
async def test_corrupted_cache_payload_falls_back_to_database(monkeypatch):
    monkeypatch.setattr(
        cache_module,
        "get_cached",
        AsyncMock(return_value={"volume_deduction_ratio": "not-a-number"}),
    )
    monkeypatch.setattr(
        DeductionConfigCache,
        "_get_generation",
        AsyncMock(return_value=7),
    )
    monkeypatch.setattr(
        DeductionConfigCache,
        "_save_to_cache",
        AsyncMock(),
    )
    expected = SimpleNamespace(
        id=9,
        offer_id=12,
        publisher_id=None,
        advertiser_id=None,
        volume_deduction_ratio=0.2,
        amount_deduction_ratio=0,
        priority=1,
        is_active=True,
        deduction_strategy="hash",
        enable_volume_deduction=True,
        enable_amount_deduction=False,
        created_at=None,
        updated_at=None,
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(expected)))

    actual = await DeductionConfigCache(db).get_config("offer", 12)

    assert actual is expected
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_query_failure_is_not_reported_as_missing_config(monkeypatch):
    monkeypatch.setattr(
        cache_module,
        "get_cached",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        DeductionConfigCache,
        "_get_generation",
        AsyncMock(return_value=7),
    )
    db_error = RuntimeError("database unavailable")
    db = SimpleNamespace(execute=AsyncMock(side_effect=db_error))

    with pytest.raises(RuntimeError, match="database unavailable"):
        await DeductionConfigCache(db).get_config("offer", 12)


@pytest.mark.asyncio
async def test_successful_empty_database_result_remains_no_config(monkeypatch):
    monkeypatch.setattr(
        cache_module,
        "get_cached",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        DeductionConfigCache,
        "_get_generation",
        AsyncMock(return_value=7),
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(None)))

    actual = await DeductionConfigCache(db).get_config("offer", 12)

    assert actual is None
    db.execute.assert_awaited_once()
