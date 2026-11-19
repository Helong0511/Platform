"""通知配置与补发对多 Client 用户的范围隔离回归测试。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import mysql

from app.models.models import UserRole
from app.services.notification.helpers import (
    assert_client_config_access,
    assert_conversion_resend_access,
    assert_notification_record_access,
    assert_product_config_access,
    get_user_client_ids,
)
from app.services.notification.queries.records_query import NotificationRecordsQuery


class _Result:
    def __init__(self, values=None, scalar_value=None):
        self.values = values or []
        self.scalar_value = scalar_value

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar(self):
        return self.scalar_value


class _DB:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)


def _client_user():
    return SimpleNamespace(id=77, role=UserRole.CLIENT)


@pytest.mark.asyncio
async def test_get_user_client_ids_returns_all_active_clients_in_stable_order():
    db = _DB([_Result([101, 202])])

    client_ids = await get_user_client_ids(db, _client_user())

    assert client_ids == [101, 202]
    sql = str(db.statements[0].compile(dialect=mysql.dialect()))
    assert "clients.user_id = 77" in sql
    assert "clients.is_active IS true" in sql
    assert "ORDER BY clients.id ASC" in sql


@pytest.mark.asyncio
async def test_non_admin_can_access_notification_resources_for_any_active_client():
    user = _client_user()

    await assert_client_config_access(_DB([_Result([101, 202])]), user, 202)
    await assert_product_config_access(
        _DB([_Result([101, 202])]), user, SimpleNamespace(client_id=202)
    )
    await assert_notification_record_access(
        _DB([_Result([101, 202])]), user, SimpleNamespace(client_id=202)
    )
    await assert_conversion_resend_access(
        _DB([_Result([101, 202])]), user, SimpleNamespace(client_id=202)
    )


@pytest.mark.asyncio
async def test_non_admin_cannot_access_unlinked_or_inactive_client_resources():
    user = _client_user()

    with pytest.raises(HTTPException):
        await assert_client_config_access(_DB([_Result([101, 202])]), user, 303)

    with pytest.raises(HTTPException):
        await assert_product_config_access(
            _DB([_Result([101, 202])]), user, SimpleNamespace(client_id=303)
        )

    with pytest.raises(HTTPException):
        await assert_notification_record_access(
            _DB([_Result([101, 202])]), user, SimpleNamespace(client_id=303)
        )

    with pytest.raises(HTTPException):
        await assert_conversion_resend_access(
            _DB([_Result([101, 202])]), user, SimpleNamespace(client_id=303)
        )


@pytest.mark.asyncio
async def test_notification_record_list_scopes_to_all_linked_client_ids():
    db = _DB([
        _Result([101, 202]),
        _Result(scalar_value=3),
        _Result([]),
    ])

    notifications, total = await NotificationRecordsQuery(db).fetch(
        current_user=_client_user()
    )

    assert notifications == []
    assert total == 3
    sql = str(db.statements[2].compile(dialect=mysql.dialect()))
    assert "postback_notifications.client_id IN (101, 202)" in sql
