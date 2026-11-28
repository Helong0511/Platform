"""CPL 扣量统计口径与应用时区回归测试。"""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.deduction import deduction_manager as deduction_manager_module
from app.core.deduction.deduction_manager import ConversionStats, DeductionManager
from app.core.utils import get_app_now_naive_floor_second
from app.models.deduction import ConversionDeductionLog
from app.models.postback import PostbackConversion
from app.services.cpl.deduction.queries.stats_query import DeductionStatsQuery


class _AllResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


@pytest.mark.asyncio
async def test_recent_stats_counts_saved_conversions_and_only_unpersisted_volume_deductions(monkeypatch):
    monkeypatch.setattr(
        deduction_manager_module,
        "get_cached",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(deduction_manager_module, "set_cached", AsyncMock())
    app_now = datetime(2026, 11, 24, 12, 0, 0)
    monkeypatch.setattr(deduction_manager_module, "get_app_now_naive", lambda: app_now)

    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _ScalarResult(120),  # 已入库的正常/扣金额转化
                _ScalarResult(8),    # 未入库的扣量命中
                _ScalarResult(3),    # 已入库且明确标记扣量的转化
            ]
        )
    )

    stats = await DeductionManager(db).get_recent_stats(
        advertiser_id=12,
        offer_id=34,
        publisher_id=56,
        hours=24,
    )

    assert stats == ConversionStats(total=128, deducted=11, processed=128)
    assert db.execute.await_count == 3

    conversion_stmt = db.execute.await_args_list[0].args[0]
    volume_log_stmt = db.execute.await_args_list[1].args[0]
    conversion_sql = str(conversion_stmt)
    volume_log_sql = str(volume_log_stmt)
    assert "postback_conversions" in conversion_sql
    assert "conversion_deduction_logs" in volume_log_sql
    # 两类数据均使用 [start_time, end_time) 半开区间，防止相邻窗口重复计算边界事件。
    assert " < " in conversion_sql
    assert " <= " not in conversion_sql
    assert " < " in volume_log_sql
    assert " <= " not in volume_log_sql
    assert "deducted_volume" in volume_log_sql
    assert "conversion_id IS NULL" in volume_log_sql

    # SQL 时间参数必须来自应用配置时区，而不是操作系统本机时区。
    conversion_params = conversion_stmt.compile().params
    assert app_now in conversion_params.values()
    assert datetime(2026, 11, 23, 12, 0, 0) in conversion_params.values()


@pytest.mark.asyncio
async def test_strict_recent_stats_bypasses_stale_cache_and_does_not_refresh_it(monkeypatch):
    stale_cache = AsyncMock(
        return_value={"total": 999, "deducted": 999, "processed": 999}
    )
    cache_write = AsyncMock()
    monkeypatch.setattr(deduction_manager_module, "get_cached", stale_cache)
    monkeypatch.setattr(deduction_manager_module, "set_cached", cache_write)
    monkeypatch.setattr(
        deduction_manager_module,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 24, 12, 0, 0),
    )

    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _ScalarResult(20),
                _ScalarResult(2),
                _ScalarResult(1),
            ]
        )
    )

    stats = await DeductionManager(db).get_recent_stats(
        advertiser_id=12,
        offer_id=34,
        publisher_id=56,
        hours=24,
        strict=True,
    )

    assert stats == ConversionStats(total=22, deducted=3, processed=22)
    stale_cache.assert_not_awaited()
    cache_write.assert_not_awaited()
    assert db.execute.await_count == 3


def test_financial_event_timestamps_are_truncated_to_mysql_datetime_precision():
    """MySQL DATETIME(0) 会舍入微秒；事件时间必须先向下截断，避免暂时落入未来。"""
    timestamp = get_app_now_naive_floor_second()

    assert timestamp.microsecond == 0
    postback_default = PostbackConversion.__table__.c.created_at.default.arg
    deduction_default = ConversionDeductionLog.__table__.c.created_at.default.arg
    assert callable(postback_default)
    assert callable(deduction_default)
    assert postback_default.__name__ == get_app_now_naive_floor_second.__name__
    assert deduction_default.__name__ == get_app_now_naive_floor_second.__name__
    # SQLAlchemy ColumnDefault 在执行时传入 ExecutionContext；直接调用时也应模拟该参数。
    assert postback_default(None).microsecond == 0
    assert deduction_default(None).microsecond == 0



def test_deduction_amount_calculation_preserves_fractional_currency_precision():
    config = SimpleNamespace(
        enable_amount_deduction=True,
        amount_deduction_ratio=Decimal("0.125"),
    )
    final_amount, deducted_amount = DeductionManager(None).calculate_amount_deduction(
        Decimal("10.1234"),
        config,
    )
    assert final_amount == Decimal("8.8580")
    assert deducted_amount == Decimal("1.2654")


def test_deduction_amount_calculation_does_not_convert_through_float():
    config = SimpleNamespace(
        enable_amount_deduction=True,
        amount_deduction_ratio=Decimal("0.333333"),
    )
    final_amount, deducted_amount = DeductionManager(None).calculate_amount_deduction(
        Decimal("123456789.123456"),
        config,
    )
    assert final_amount + deducted_amount == Decimal("123456789.123456")
    assert isinstance(final_amount, Decimal)
    assert isinstance(deducted_amount, Decimal)


def test_deduction_export_formatter_keeps_three_and_six_decimal_values():
    from app.services.cpl.deduction.mappers import _format_amount

    assert _format_amount(Decimal("12.345")) == "12.345"
    assert _format_amount(Decimal("12.345678")) == "12.345678"
    assert _format_amount(Decimal("12.000000")) == "12.000000"



@pytest.mark.asyncio
async def test_deduction_stats_query_preserves_decimal_currency_totals():
    row = SimpleNamespace(
        currency="KWD",
        currency_source="offer",
        original_volume=10,
        deducted_volume=2,
        final_volume=8,
        original_amount=Decimal("123.456789"),
        deducted_amount=Decimal("12.345678"),
        final_amount=Decimal("111.111111"),
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=_AllResult([row])))

    result = await DeductionStatsQuery(db).fetch(
        start_date="2026-11-01",
        end_date="2026-11-26",
    )

    assert result["original_amount"] == Decimal("123.456789")
    assert result["deducted_amount"] == Decimal("12.345678")
    assert result["final_amount"] == Decimal("111.111111")
    assert result["amount_deduction_ratio"] == (
        Decimal("12.345678") / Decimal("123.456789")
    )
    assert result["currency_summaries"][0]["currency"] == "KWD"
    assert result["currency_summaries"][0]["currency_source"] == "offer"
    assert isinstance(result["currency_summaries"][0]["original_amount"], Decimal)

    
@pytest.mark.asyncio
async def test_deduction_stats_separates_same_currency_by_source_and_keeps_unknown_explicit():
    rows = [
        SimpleNamespace(currency="USD", currency_source="offer", original_volume=2, deducted_volume=0, final_volume=2, original_amount=Decimal("10"), deducted_amount=Decimal("0"), final_amount=Decimal("10")),
        SimpleNamespace(currency="USD", currency_source="publisher", original_volume=3, deducted_volume=1, final_volume=2, original_amount=Decimal("20"), deducted_amount=Decimal("2"), final_amount=Decimal("18")),
        SimpleNamespace(currency=None, currency_source=None, original_volume=1, deducted_volume=0, final_volume=1, original_amount=Decimal("5"), deducted_amount=Decimal("0"), final_amount=Decimal("5")),
    ]
    db = SimpleNamespace(execute=AsyncMock(return_value=_AllResult(rows)))
    result = await DeductionStatsQuery(db).fetch(start_date="2026-11-01", end_date="2026-11-26")
    assert len(result["currency_summaries"]) == 3
    assert {(x["currency"], x["currency_source"]) for x in result["currency_summaries"]} == {
        ("USD", "offer"), ("USD", "publisher"), ("LEGACY_UNKNOWN", "legacy_unknown")
    }
    assert result["original_amount"] is None
    assert result["deducted_amount"] is None
    assert result["amount_deduction_ratio"] is None


def test_deduction_stats_response_rejects_missing_currency_source():
    from pydantic import ValidationError
    from app.schemas.cpl.deduction import DeductionStatsResponse

    with pytest.raises(ValidationError):
        DeductionStatsResponse(currency_summaries=[{"currency": "USD", "original_amount": Decimal("1")}])

    

def test_deduction_stats_export_keeps_same_currency_sources_separate():
    from app.schemas.cpl.deduction import DeductionStatsResponse
    from app.services.cpl.deduction.mappers import stats_to_export_rows

    stats = DeductionStatsResponse(
        original_volume=5,
        deducted_volume=1,
        final_volume=4,
        original_amount=None,
        deducted_amount=None,
        final_amount=None,
        amount_deduction_ratio=None,
        currency_summaries=[
            {
                "currency": "USD",
                "currency_source": "offer",
                "original_volume": 2,
                "deducted_volume": 0,
                "final_volume": 2,
                "original_amount": Decimal("10"),
                "deducted_amount": Decimal("0"),
                "final_amount": Decimal("10"),
                "amount_deduction_ratio": Decimal("0"),
            },
            {
                "currency": "USD",
                "currency_source": "publisher",
                "original_volume": 3,
                "deducted_volume": 1,
                "final_volume": 2,
                "original_amount": Decimal("20"),
                "deducted_amount": Decimal("2"),
                "final_amount": Decimal("18"),
                "amount_deduction_ratio": Decimal("0.1"),
            },
        ],
    )

    rows = stats_to_export_rows(stats)
    assert rows[0]["原始转化金额"] == "多币种，见分币种明细"
    assert [(row["币种"], row["币种来源"]) for row in rows[1:]] == [
        ("USD", "offer"),
        ("USD", "publisher"),
    ]

    
@pytest.mark.asyncio
async def test_legacy_unknown_source_never_becomes_usd_even_after_backfill():
    rows = [
        SimpleNamespace(currency="USD", currency_source="legacy_unknown", original_volume=1, deducted_volume=0, final_volume=1, original_amount=Decimal("5"), deducted_amount=Decimal("0"), final_amount=Decimal("5")),
        SimpleNamespace(currency="EUR", currency_source="legacy_unknown", original_volume=1, deducted_volume=0, final_volume=1, original_amount=Decimal("3"), deducted_amount=Decimal("0"), final_amount=Decimal("3")),
    ]
    db = SimpleNamespace(execute=AsyncMock(return_value=_AllResult(rows)))
    result = await DeductionStatsQuery(db).fetch(start_date="2026-11-01", end_date="2026-11-26")
    assert len(result["currency_summaries"]) == 2
    assert all(item["currency"] == "LEGACY_UNKNOWN" for item in result["currency_summaries"])
    assert all(item["currency_source"] == "legacy_unknown" for item in result["currency_summaries"])
    statement = db.execute.await_args.args[0]
    assert "CASE WHEN" in str(statement).upper()
