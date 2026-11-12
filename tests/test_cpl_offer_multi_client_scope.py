"""CPL Offer 多客户账号数据范围回归测试。"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql

from app.api_v1.cpl.offers import _sanitize_offer_response_for_client
from app.models.models import UserRole
from app.services.cpl.offer.helpers import (
    assert_client_can_access_offer,
    get_client_ids_for_user,
)
from app.services.cpl.offer.queries.list_query import OfferListQuery


class _Result:
    def __init__(self, *, values=None, scalar=None, rows=None, unique_rows=None):
        self.values = values
        self.scalar_value = scalar
        self.rows = rows
        self.unique_rows = unique_rows

    def scalars(self):
        return self

    def all(self):
        return self.values if self.values is not None else (self.rows if self.rows is not None else self.unique_rows or [])

    def scalar(self):
        return self.scalar_value

    def scalar_one_or_none(self):
        return self.scalar_value

    def unique(self):
        return self

    def first(self):
        return self.scalar_value

    def __iter__(self):
        return iter(self.unique_rows or [])


class _FakeDB:
    def __init__(self, responses):
        self.responses = list(responses)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.responses.pop(0)


def _client_user():
    return SimpleNamespace(id=77, role=UserRole.CLIENT)


def _sql(statement):
    return str(
        statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


@pytest.mark.asyncio
async def test_get_client_ids_for_user_returns_all_memberships():
    db = _FakeDB([_Result(values=[10, 20, 30])])

    client_ids = await get_client_ids_for_user(db, _client_user())

    assert client_ids == [10, 20, 30]
    assert "clients.user_id = 77" in _sql(db.statements[0])
    assert "clients.is_active = true" in _sql(db.statements[0])


@pytest.mark.asyncio
async def test_assert_client_offer_access_checks_all_client_memberships():
    db = _FakeDB([
        _Result(values=[10, 20]),
        _Result(scalar=object()),
    ])

    await assert_client_can_access_offer(db, offer_id=501, user=_client_user())

    query_sql = _sql(db.statements[1])
    assert "publishers.client_id IN (10, 20)" in query_sql
    assert "offer_publisher_assignments.is_active = true" in query_sql


@pytest.mark.asyncio
async def test_offer_list_and_assignment_map_include_all_client_memberships():
    offer = SimpleNamespace(
        id=501,
        created_at=datetime(2026, 1, 1),
        advertiser=None,
    )
    assignment = SimpleNamespace(
        offer_id=501,
        downstream_cap=100,
        affiliate_payout=2.5,
    )
    publisher_a = SimpleNamespace(
        id=1001,
        publisher_name="client-a-publisher",
        client_id=10,
    )
    publisher_b = SimpleNamespace(
        id=1002,
        publisher_name="client-b-publisher",
        client_id=20,
    )
    db = _FakeDB([
        _Result(values=[10, 20]),                  # Offer list client IDs
        _Result(scalar=1),                         # Count query
        _Result(unique_rows=[offer]),              # Offer page query
        _Result(values=[10, 20]),                  # Assignment batch client IDs
        _Result(rows=[(assignment, publisher_a), (assignment, publisher_b)]),
    ])

    offers, total, assignments = await OfferListQuery(db).fetch(
        current_user=_client_user(),
        page=1,
        page_size=20,
    )

    assert offers == [offer]
    assert total == 1
    assert {item["client_id"] for item in assignments[501]} == {10, 20}
    count_sql = _sql(db.statements[1])
    page_sql = _sql(db.statements[2])
    assignment_sql = _sql(db.statements[4])
    assert "publishers.client_id IN (10, 20)" in count_sql
    assert "publishers.client_id IN (10, 20)" in page_sql
    assert "publishers.client_id IN (10, 20)" in assignment_sql


def test_client_offer_response_sanitizer_keeps_all_owned_clients_only():
    response = SimpleNamespace(
        advertiser_id=1,
        advertiser_name="upstream-private",
        advertiser_offer_id="upstream-id",
        payout=10,
        upstream_cap=1000,
        affiliate_payout=8,
        downstream_cap=500,
        advertiser_tracklink="https://upstream.invalid",
        postback_url="https://internal.invalid",
        assigned_publishers=[
            {"id": 1, "client_id": 10},
            {"id": 2, "client_id": 20},
            {"id": 3, "client_id": 30},
        ],
    )

    sanitized = _sanitize_offer_response_for_client(
        response,
        _client_user(),
        client_ids=[10, 20],
    )

    assert [item["client_id"] for item in sanitized.assigned_publishers] == [10, 20]
    assert sanitized.advertiser_id is None
    assert sanitized.payout is None
    assert sanitized.advertiser_tracklink is None
    assert sanitized.postback_url is None
