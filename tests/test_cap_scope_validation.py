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

    def unique(self):
        return self


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


@pytest.mark.asyncio
async def test_update_cap_rejects_in_place_counter_scope_migration():
    """Changing the Offer/publisher scope must not carry the old counter baseline."""
    existing = SimpleNamespace(
        id=5,
        cap_type="offer",
        advertiser_id=None,
        offer_id=10,
        publisher_id=3,
        cap_start_date=None,
        daily_cap=100,
        total_cap=500,
        is_active=True,
    )

    class _UpdateDB:
        async def execute(self, statement):
            return _Result(rows=[existing])

    service = _service(_UpdateDB())
    with pytest.raises(HTTPException) as exc:
        await service.update_cap(
            cap_id=5,
            update_data={"publisher_id": 9},
            current_user=SimpleNamespace(id=1),
        )

    assert "不允许原地修改 Cap 的归属范围" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_delete_cap_locks_row_before_deleting_orm_entity():
    existing = SimpleNamespace(
        id=42,
        cap_type="offer",
        advertiser_id=None,
        offer_id=10,
        publisher_id=3,
        daily_cap=100,
        total_cap=500,
        current_daily_count=8,
        current_total_count=30,
        cap_start_date=None,
        is_active=True,
    )
    class _DeleteDB:
        def __init__(self):
            self.statement = None
            self.deleted = []
            self.flushed = False

        async def execute(self, statement):
            self.statement = str(statement).lower()
            return _Result(rows=[existing])

        async def delete(self, entity):
            self.deleted.append(entity)

        async def flush(self):
            self.flushed = True

    db = _DeleteDB()
    snapshot = await _service(db).delete_cap(42, current_user=SimpleNamespace(id=1))

    assert snapshot["cap_id"] == 42
    assert snapshot["offer_id"] == 10
    assert snapshot["publisher_id"] == 3
    assert snapshot["current_total_count"] == 30
    assert "for update" in db.statement
    assert db.deleted == [existing]
    assert db.flushed is True


@pytest.mark.asyncio
async def test_update_cap_captures_before_values_under_row_lock():
    existing = SimpleNamespace(
        id=6,
        cap_type="offer",
        advertiser_id=None,
        offer_id=10,
        publisher_id=3,
        cap_start_date=None,
        daily_cap=100,
        total_cap=500,
        current_daily_count=12,
        current_total_count=40,
        is_active=True,
    )

    class _UpdateAuditDB:
        def __init__(self):
            self.statements = []
            self.flushed = False

        async def execute(self, statement):
            sql = str(statement).lower()
            self.statements.append(sql)
            if "from offers" in sql:
                return _Result(rows=[SimpleNamespace(id=10, advertiser_id=7)])
            if "from publishers" in sql:
                return _Result(scalar=3)
            if "from offer_caps" in sql:
                # 初始锁定查询、重复范围校验、joinedload 回查均返回既有记录；
                # 重复校验通过 scalar_one_or_none() 读取 None。
                if "offer_caps.id !=" in sql or "offer_caps.id <>" in sql:
                    return _Result(scalar=None)
                if "offer_caps.id =" in sql and "join" not in sql:
                    return _Result(rows=[existing])
                return _Result(rows=[existing])
            raise AssertionError(f"unexpected SQL: {sql}")

        async def flush(self):
            self.flushed = True

        async def refresh(self, entity):
            return None

    db = _UpdateAuditDB()
    updated = await _service(db).update_cap(
        cap_id=6,
        update_data={"daily_cap": 120},
        current_user=SimpleNamespace(id=1),
    )

    assert db.flushed is True
    assert updated.daily_cap == 120
    assert updated._audit_before == {"daily_cap": 100}
    assert any("for update" in sql for sql in db.statements)
