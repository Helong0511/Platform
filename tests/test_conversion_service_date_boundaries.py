"""转化按 Offer 汇总的日期边界回归测试。"""
from datetime import datetime

from app.services.cpl import conversion_service


def test_by_offer_end_date_uses_exclusive_next_midnight(monkeypatch):
    """结束日期应覆盖当天 23:59:59.999999，而不是截断到整秒。"""
    monkeypatch.setattr(
        conversion_service,
        "parse_date_to_app_timezone",
        lambda value, is_end_date=False: datetime(2026, 11, 11, 0, 0, 0),
    )

    assert conversion_service._exclusive_end_datetime("2026-11-11") == datetime(
        2026, 11, 12, 0, 0, 0
    )
