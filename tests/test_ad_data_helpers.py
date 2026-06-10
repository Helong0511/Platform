"""
广告数据 validators / uniqueness 单元测试（无数据库依赖部分）。
"""
from datetime import date, datetime

from app.services.ad_data.queries.uniqueness_query import AdDataUniquenessQuery
from app.services.ad_data.validators import AdDataValidator, UPDATE_ALLOWED_FIELDS


def test_filter_update_fields_whitelist():
    raw = {
        "product_id": 1,
        "request_count": 100,
        "evil_field": "drop table",
        "ad_unit": "  unit-a  ",
    }
    filtered = AdDataValidator.filter_update_fields(raw)
    assert "evil_field" not in filtered
    assert filtered["product_id"] == 1
    assert filtered["request_count"] == 100
    assert filtered["ad_unit"] == "unit-a"


def test_needs_uniqueness_check():
    assert AdDataValidator.needs_uniqueness_check({"product_id": 2}) is True
    assert AdDataValidator.needs_uniqueness_check({"country_code": "US"}) is True
    assert AdDataValidator.needs_uniqueness_check({"request_count": 1}) is False
    assert AdDataValidator.needs_uniqueness_check({"ad_unit": "x"}) is False


def test_uniqueness_day_bounds_datetime():
    dt = datetime(2024, 3, 15, 14, 30, 0)
    start, end = AdDataUniquenessQuery._day_bounds(dt)
    assert start == datetime(2024, 3, 15, 0, 0, 0)
    assert end.hour == 23 and end.minute == 59


def test_uniqueness_day_bounds_date():
    d = date(2024, 3, 15)
    start, end = AdDataUniquenessQuery._day_bounds(d)
    assert start.date() == d
    assert end.date() == d


def test_update_allowed_fields_contains_core_keys():
    for key in ("product_id", "country_code", "ad_unit", "request_count"):
        assert key in UPDATE_ALLOWED_FIELDS


def test_batch_delete_command_rejects_empty_ids():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import pytest
    from fastapi import HTTPException

    from app.core.errors import ErrorCode
    from app.services.ad_data.commands.delete_command import AdDataBatchDeleteCommand

    cmd = AdDataBatchDeleteCommand(db=AsyncMock())
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(cmd.execute([], MagicMock()))
    assert exc_info.value.detail["code"] == ErrorCode.AD_DATA_EMPTY_SELECTION
