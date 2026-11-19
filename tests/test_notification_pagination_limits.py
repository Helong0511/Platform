"""通知记录列表深分页与稳定排序回归测试。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import mysql

from app.models.models import UserRole
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


def _admin():
    return SimpleNamespace(id=1, role=UserRole.ADMIN)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page", "page_size"),
    [(0, 20), (1, 101), (1002, 100)],
)
async def test_notification_query_rejects_invalid_or_deep_pagination_before_db(
    page,
    page_size,
):
    db = _DB([])

    with pytest.raises(HTTPException):
        await NotificationRecordsQuery(db).fetch(
            page=page,
            page_size=page_size,
            current_user=_admin(),
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_notification_query_allows_exact_offset_boundary_and_uses_stable_order():
    record = SimpleNamespace(id=900001)
    db = _DB([
        _Result(scalar_value=100001),
        _Result([record]),
    ])

    notifications, total = await NotificationRecordsQuery(db).fetch(
        page=1001,
        page_size=100,
        current_user=_admin(),
    )

    assert notifications == [record]
    assert total == 100001
    sql = str(
        db.statements[1].compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert (
        "ORDER BY postback_notifications.created_at DESC, "
        "postback_notifications.id DESC"
    ) in sql
