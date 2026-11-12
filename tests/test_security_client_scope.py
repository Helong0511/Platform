"""客户权限守卫必须覆盖用户关联的全部 Client 记录。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import mysql

from app.core.security import require_publisher_or_admin
from app.models.models import UserRole


class _ClientRows:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class _PublisherScalar:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DB:
    def __init__(self, client_ids, publisher_id):
        self.client_ids = client_ids
        self.publisher_id = publisher_id
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement.compile(dialect=mysql.dialect())).lower())
        if len(self.statements) == 1:
            return _ClientRows(self.client_ids)
        return _PublisherScalar(self.publisher_id)


@pytest.mark.asyncio
async def test_publisher_guard_accepts_active_publisher_on_any_owned_client():
    user = SimpleNamespace(id=906, role=UserRole.CLIENT)
    db = _DB(client_ids=[101, 202], publisher_id=303)

    result = await require_publisher_or_admin(current_user=user, db=db)

    assert result is user
    assert len(db.statements) == 2
    assert "clients.user_id = %s" in db.statements[0]
    assert "clients.is_active = true" in db.statements[0]
    assert "publishers.client_id in" in db.statements[1]
    assert "publishers.is_active" in db.statements[1]


@pytest.mark.asyncio
async def test_publisher_guard_denies_client_user_without_any_client_record():
    user = SimpleNamespace(id=907, role=UserRole.CLIENT)
    db = _DB(client_ids=[], publisher_id=None)

    with pytest.raises(HTTPException) as exc:
        await require_publisher_or_admin(current_user=user, db=db)

    assert exc.value.status_code == 403
    assert len(db.statements) == 1


@pytest.mark.asyncio
async def test_publisher_guard_denies_when_no_owned_client_has_active_publisher():
    user = SimpleNamespace(id=908, role=UserRole.CLIENT)
    db = _DB(client_ids=[101, 202], publisher_id=None)

    with pytest.raises(HTTPException) as exc:
        await require_publisher_or_admin(current_user=user, db=db)

    assert exc.value.status_code == 403
    assert len(db.statements) == 2
    assert "publishers.client_id in" in db.statements[1]
