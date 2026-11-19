"""广告数据明细和每日汇总分页预算回归测试。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import literal, select
from sqlalchemy.dialects import mysql

from app.models.models import UserRole
from app.services.ad_data.queries import daily_summary_query, list_query
from app.services.ad_data.queries.daily_summary_query import DailySummaryQuery
from app.services.ad_data.queries.list_query import AdDataListQuery


class _Result:
    def __init__(self, rows=None):
        self.rows = rows or []

    def unique(self):
        return self

    def all(self):
        return self.rows


class _DB:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result([])


def _admin():
    return SimpleNamespace(id=1, role=UserRole.ADMIN)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page", "page_size"),
    [(0, 10), (1, 101), (1002, 100)],
)
async def test_ad_data_list_rejects_invalid_or_deep_pagination_before_db(page, page_size):
    db = _DB()

    with pytest.raises(HTTPException):
        await AdDataListQuery(db).fetch(
            current_user=_admin(),
            page=page,
            page_size=page_size,
        )

    assert db.statements == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page", "page_size"),
    [(0, 10), (1, 101), (1002, 100)],
)
async def test_daily_summary_rejects_invalid_or_deep_pagination_before_cache_or_db(
    page,
    page_size,
    monkeypatch,
):
    db = _DB()

    async def unexpected_fetch(**kwargs):
        raise AssertionError("deep pagination must be rejected before cache/DB work")

    monkeypatch.setattr(DailySummaryQuery, "_fetch_uncached", unexpected_fetch)

    with pytest.raises(HTTPException):
        await DailySummaryQuery(db).fetch(
            current_user=_admin(),
            page=page,
            page_size=page_size,
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_ad_data_list_allows_exact_offset_boundary(monkeypatch):
    db = _DB()
    query = AdDataListQuery(db)

    async def no_assignment_table(_db):
        return False

    async def build_main_query(*args, **kwargs):
        return select(literal(1))

    async def count_total(*args, **kwargs):
        return 100001

    monkeypatch.setattr(list_query, "check_use_assignment_table", no_assignment_table)
    monkeypatch.setattr(query, "_build_main_query", build_main_query)
    monkeypatch.setattr(query, "_apply_sort", lambda statement, *args: statement)
    monkeypatch.setattr(query, "_count_total", count_total)
    monkeypatch.setattr(query, "_build_responses", lambda rows, *args: rows)

    rows, total = await query.fetch(
        current_user=_admin(),
        page=1001,
        page_size=100,
    )

    assert rows == []
    assert total == 100001
    sql = str(
        db.statements[0].compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "OFFSET 100000" in sql


@pytest.mark.asyncio
async def test_daily_summary_allows_exact_offset_boundary(monkeypatch):
    db = _DB()
    query = DailySummaryQuery(db)
    expected_items = [{"date": "2026-11-19"}]

    async def fetch_uncached(**kwargs):
        assert kwargs["page"] == 1001
        assert kwargs["page_size"] == 100
        return expected_items, 100001, {"total_revenue": 1}

    monkeypatch.setattr(query, "_fetch_uncached", fetch_uncached)

    items, total, grand_total = await query.fetch(
        current_user=_admin(),
        page=1001,
        page_size=100,
        skip_cache=True,
    )

    assert items == expected_items
    assert total == 100001
    assert grand_total == {"total_revenue": 1}
    assert db.statements == []
