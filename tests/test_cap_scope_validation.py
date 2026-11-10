"""Cap scope validation must enforce Offer ownership and prevent duplicate scopes."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.cpl.cap_service import CapService


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None


class _Result:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or []
        self.scalar = scalar

    def scalars(self):
        return _Scalars(self.rows)

    def scalar_one_or_none(self):
        return self.scalar


class _ScopeDB:
    def __init__(self, *, offer_advertiser_id=7, publisher_exists=True, duplicate_id=None):
        self.offer_advertiser_id = offer_advertiser_id
        self.publisher_exists = publisher_exists
        self.duplicate_id = duplicate_id
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement).lower())
        sql = self.statements[-1]
        if "from offers" in sql:
            return _Result(rows=[SimpleNamespace(id=10, advertiser_id=self.offer_advertiser_id)])
        if "from publishers" in sql:
            return _Result(scalar=3 if self.publisher_exists else None)
        if "from offer_caps" in sql:
            return _Result(scalar=self.duplicate_id)
        raise AssertionError(f"unexpected SQL: {sql}")


def _service(db):
    service = object.__new__(CapService)
    service.db = db
    return service


@pytest.mark.asyncio
async def test_advertiser_offer_cap_requires_matching_offer_owner():
    db = _ScopeDB(offer_advertiser_id=7)
    await _service(db)._validate_cap_scope({
        "cap_type": "advertiser_offer",
        "advertiser_id": 7,
        "offer_id": 10,
        "publisher_id": 3,
    })
    assert any("from offers" in sql and "for update" in sql for sql in db.statements)
    assert any("from publishers" in sql for sql in db.statements)
    assert any("from offer_caps" in sql for sql in db.statements)


@pytest.mark.asyncio
async def test_advertiser_offer_cap_rejects_unrelated_advertiser():
    db = _ScopeDB(offer_advertiser_id=7)
    with pytest.raises(HTTPException):
        await _service(db)._validate_cap_scope({
            "cap_type": "advertiser_offer",
            "advertiser_id": 99,
            "offer_id": 10,
            "publisher_id": None,
        })
    assert not any(" from offer_caps" in sql for sql in db.statements)


@pytest.mark.asyncio
async def test_offer_global_cap_rejects_advertiser_id():
    with pytest.raises(HTTPException):
        await _service(_ScopeDB())._validate_cap_scope({
            "cap_type": "offer",
            "advertiser_id": 7,
            "offer_id": 10,
            "publisher_id": None,
        })


@pytest.mark.asyncio
async def test_cap_scope_rejects_duplicate_even_if_existing_record_is_inactive():
    db = _ScopeDB(duplicate_id=123)
    with pytest.raises(HTTPException):
        await _service(db)._validate_cap_scope({
            "cap_type": "offer",
            "advertiser_id": None,
            "offer_id": 10,
            "publisher_id": None,
        })


@pytest.mark.asyncio
async def test_cap_scope_rejects_unknown_cap_type():
    with pytest.raises(HTTPException):
        await _service(_ScopeDB())._validate_cap_scope({
            "cap_type": "unexpected",
            "advertiser_id": None,
            "offer_id": 10,
            "publisher_id": None,
        })
