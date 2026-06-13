"""产品分配覆盖与 Telegram 告警文案测试。"""
from sqlalchemy.dialects import mysql

from app.core.product_assignment import (
    _assignment_covers_ad_data_date_condition,
    format_assignment_gap_telegram_message,
)
from app.models.models import AdData, ProductAssignment
from sqlalchemy import exists, func, select


def test_find_ad_data_assignment_gaps_exists_has_from_clause():
    """EXISTS 子查询须显式 FROM product_assignments，避免依赖 SQLAlchemy 推断。"""
    has_assignment = exists(
        select(1)
        .select_from(ProductAssignment)
        .where(_assignment_covers_ad_data_date_condition())
    )
    query = (
        select(func.count(AdData.id))
        .select_from(AdData)
        .where(func.date(AdData.date) >= "2026-06-01", ~has_assignment)
    )
    sql = str(query.compile(dialect=mysql.dialect()))
    assert "EXISTS" in sql
    assert "product_assignments" in sql


def test_format_assignment_gap_telegram_message():
    gaps = [
        {
            "product_name": "https://game2.ibobin.com/",
            "data_date": "2026-06-13",
            "row_count": 59,
        }
    ]
    msg = format_assignment_gap_telegram_message(
        notify_title="yangyangdeyi",
        gaps=gaps,
        total_orphan=59,
    )
    assert "产品分配覆盖异常" in msg
    assert "game2.ibobin.com" in msg
    assert "59 条" in msg
    assert "自动补全" not in msg


def test_format_assignment_gap_truncates_list():
    gaps = [{"product_name": "p1", "data_date": "2026-06-13", "row_count": 10}]
    msg = format_assignment_gap_telegram_message(
        notify_title="test",
        gaps=gaps,
        total_orphan=100,
    )
    assert "其余 90 条未列出" in msg
