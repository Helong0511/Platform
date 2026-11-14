"""多客户账号获取开放 API 密钥时必须显式选择客户。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api_v1.external import client_api
from app.models.models import UserRole


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class _DB:
    def __init__(self, values):
        self.values = values
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.values)


def _user():
    return SimpleNamespace(id=77, role=UserRole.CLIENT)


@pytest.mark.asyncio
async def test_multi_client_api_key_requires_explicit_client_id():
    db = _DB([
        SimpleNamespace(id=10, key="client-key-10", api_enabled=True),
        SimpleNamespace(id=20, key="client-key-20", api_enabled=True),
    ])

    with pytest.raises(HTTPException) as caught:
        await client_api.get_client_api_key(
            client_id=None,
            current_user=_user(),
            db=db,
        )

    assert "多个客户" in str(caught.value.detail)


@pytest.mark.asyncio
async def test_multi_client_api_key_returns_only_explicitly_selected_client():
    db = _DB([
        SimpleNamespace(id=20, key="client-key-20", api_enabled=True),
    ])

    response = await client_api.get_client_api_key(
        client_id=20,
        current_user=_user(),
        db=db,
    )

    assert response.data == {"client_id": 20, "key": "client-key-20"}
    sql = str(db.statements[0])
    assert "clients.user_id" in sql
    assert "clients.id" in sql


@pytest.mark.asyncio
async def test_single_client_api_key_remains_backward_compatible():
    db = _DB([
        SimpleNamespace(id=10, key="legacy-single-client-key", api_enabled=True),
    ])

    response = await client_api.get_client_api_key(
        client_id=None,
        current_user=_user(),
        db=db,
    )

    assert response.data == {
        "client_id": 10,
        "key": "legacy-single-client-key",
    }


@pytest.mark.asyncio
async def test_client_cannot_fetch_another_users_api_key():
    db = _DB([])

    with pytest.raises(HTTPException):
        await client_api.get_client_api_key(
            client_id=999,
            current_user=_user(),
            db=db,
        )
