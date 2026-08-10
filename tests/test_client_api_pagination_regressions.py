from __future__ import annotations

from datetime import date
from decimal import Decimal
import inspect
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

import app.services.ad_data.queries.client_api_query as client_query_module
from app.api_v1.external.client_api import ClientDataRequest
from app.core.constants import CLIENT_API_MAX_PAGE
from app.models.models import AdData, Product
from app.services.ad_data.queries.client_api_query import ClientAdDataQuery
from app.services.ad_data.queries.dimension_filter import (
    DETAIL_ALL_DIMENSION,
    build_ad_data_dimension_filter,
    ensure_valid_optional_dimension,
    parse_optional_dimension,
)
from app.services.ad_data.queries.join_helpers import best_product_assignment_id_subquery


def test_raw_all_dimension_is_explicit_and_valid():
    assert ensure_valid_optional_dimension("all") == DETAIL_ALL_DIMENSION
    assert parse_optional_dimension("all") == DETAIL_ALL_DIMENSION


def test_request_rejects_page_above_hard_limit():
    with pytest.raises(ValueError):
        ClientDataRequest(
            client_id=1,
            req_time=1,
            sign="x",
            page=CLIENT_API_MAX_PAGE + 1,
        )


def test_assignment_selector_is_global_and_requester_independent():
    assert "preferred_client_id" not in inspect.signature(
        best_product_assignment_id_subquery
    ).parameters
    expr = best_product_assignment_id_subquery(AdData.date, Product.id)
    sql = str(expr.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "case" not in sql
    assert "order by" in sql
    assert ".id asc" in sql


@pytest.mark.asyncio
async def test_detail_without_dimension_defaults_to_country(monkeypatch):
    captured = {}

    async def fake_assignment_check(_db):
        return False

    async def fake_detail(
        self,
        client,
        start_date,
        end_date,
        use_assignment_table,
        dimension,
        offset,
        page_size,
    ):
        captured["dimension"] = dimension
        captured["offset"] = offset
        captured["page_size"] = page_size
        return [], 0

    monkeypatch.setattr(client_query_module, "check_use_assignment_table", fake_assignment_check)
    monkeypatch.setattr(ClientAdDataQuery, "_fetch_detail", fake_detail)

    rows, total = await ClientAdDataQuery(db=object()).fetch(
        client=SimpleNamespace(id=1),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
        data_type="all",
        dimension=None,
        page=CLIENT_API_MAX_PAGE + 10,
        page_size=1,
    )

    assert rows == []
    assert total == 0
    assert captured == {
        "dimension": "country",
        "offset": CLIENT_API_MAX_PAGE - 1,
        "page_size": 1,
    }


@pytest.mark.asyncio
async def test_detail_row_null_counts_and_rates_are_safe(monkeypatch):
    ad_data = SimpleNamespace(
        id=1,
        product_id=2,
        date=date(2026, 8, 1),
        country_code="US",
        ad_unit=" unit-a ",
        request_count=None,
        match_count=None,
        coverage_rate=None,
        display_count=None,
        display_rate=None,
        click_count=None,
        click_rate=None,
        viewability_rate=None,
        cpc=None,
        pageviews=None,
        ecpm_after_deduct=None,
        revenue_after_deduct=None,
    )

    class FakeResult:
        def all(self):
            return [(ad_data, "P1", 1)]

    class FakeDb:
        async def execute(self, _query):
            return FakeResult()

    async def fake_country_names(_codes):
        return {}

    query = ClientAdDataQuery(FakeDb())
    monkeypatch.setattr(query, "_load_country_name_zh", fake_country_names)
    rows, total = await query._fetch_detail(
        client=SimpleNamespace(id=1),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
        use_assignment_table=False,
        dimension="all",
        offset=0,
        page_size=10,
    )

    assert total == 1
    assert len(rows) == 1
    assert rows[0]["ad_unit"] == "unit-a"
    assert rows[0]["request_count"] == 0
    assert rows[0]["match_count"] == 0
    assert rows[0]["display_count"] == 0
    assert rows[0]["click_count"] == 0
    assert rows[0]["coverage_rate"] == Decimal("0.00")
    assert rows[0]["display_rate"] == Decimal("0.00")
    assert rows[0]["click_rate"] == Decimal("0.00")


def test_country_and_ad_unit_identity_duplicate_filter_keeps_canonical_id():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE ad_data (
                id INTEGER PRIMARY KEY,
                date DATE NOT NULL,
                product_id INTEGER NOT NULL,
                country_code VARCHAR(100),
                ad_unit VARCHAR(150),
                data_source VARCHAR(32),
                report_type VARCHAR(16),
                upstream_account VARCHAR(64)
            )
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO ad_data
                (id, date, product_id, country_code, ad_unit, data_source, report_type, upstream_account)
            VALUES
                (1, '2026-08-01', 1, NULL, NULL, NULL, NULL, NULL),
                (2, '2026-08-01', 1, '', NULL, NULL, NULL, NULL),
                (3, '2026-08-01', 1, ' ZZ ', NULL, NULL, NULL, NULL),
                (4, '2026-08-01', 1, ' US ', '', 'api', 'country', ''),
                (5, '2026-08-01', 1, 'US', '', 'api', 'country', ''),
                (6, '2026-08-01', 1, 'US', '', 'api', 'country', 'other'),
                (7, '2026-08-01', 1, 'CN', ' unit-a ', 'api', 'cross', ''),
                (8, '2026-08-01', 1, 'CN', 'unit-a', 'api', 'cross', '')
            """
        )
        query = ClientAdDataQuery._apply_country_identity_dedup(
            select(AdData.id)
        ).order_by(AdData.id)
        ids = list(conn.execute(query).scalars())

    assert ids == [1, 5, 6, 8]


def test_dimension_filter_trims_country_and_ad_unit_whitespace():
    metadata = MetaData()
    shape = Table(
        "shape",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("country_code", String),
        Column("ad_unit", String),
    )
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            shape.insert(),
            [
                {"id": 1, "country_code": " US ", "ad_unit": "   "},
                {"id": 2, "country_code": " ZZ ", "ad_unit": " unit-a "},
                {"id": 3, "country_code": "   ", "ad_unit": " unit-b "},
            ],
        )
        country_ids = list(
            conn.execute(
                select(shape.c.id)
                .where(
                    build_ad_data_dimension_filter(
                        shape.c.country_code,
                        shape.c.ad_unit,
                        "country",
                    )
                )
                .order_by(shape.c.id)
            ).scalars()
        )
        ad_unit_ids = list(
            conn.execute(
                select(shape.c.id)
                .where(
                    build_ad_data_dimension_filter(
                        shape.c.country_code,
                        shape.c.ad_unit,
                        "ad_unit",
                    )
                )
                .order_by(shape.c.id)
            ).scalars()
        )

    assert country_ids == [1]
    assert ad_unit_ids == [2, 3]


@pytest.mark.asyncio
async def test_grouped_page_uses_one_query_for_rows_and_total():
    row = SimpleNamespace(date=date(2026, 8, 1), product_id=1, _total=3)

    class FakeResult:
        def all(self):
            return [row]

    class FakeDb:
        def __init__(self):
            self.calls = 0

        async def execute(self, _query):
            self.calls += 1
            return FakeResult()

    db = FakeDb()
    grouped = select(
        AdData.date.label("date"),
        AdData.product_id.label("product_id"),
    ).group_by(AdData.date, AdData.product_id)

    rows, total = await ClientAdDataQuery(db)._paginate_grouped_query(
        grouped,
        offset=0,
        page_size=10,
    )

    assert rows == [row]
    assert total == 3
    assert db.calls == 1
