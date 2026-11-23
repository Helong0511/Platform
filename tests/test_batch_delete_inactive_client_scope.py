"""
广告数据批量删除必须与详情查询采用相同的启用客户范围。
"""
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql

from app.models.models import UserRole
from app.services.ad_data.queries import batch_delete_query


class _Rows:
    def unique(self):
        return self

    def all(self):
        return []


class _DB:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = str(statement.compile(dialect=mysql.dialect())).lower()
        return _Rows()


@pytest.mark.asyncio
async def test_batch_delete_scope_excludes_inactive_clients(monkeypatch):
    async def use_legacy_client_relation(_db):
        return False

    monkeypatch.setattr(
        batch_delete_query,
        "check_use_assignment_table",
        use_legacy_client_relation,
    )
    db = _DB()
    user = SimpleNamespace(id=910, username="tenant-user", role=UserRole.CLIENT)

    result = await batch_delete_query.BatchDeleteQuery(db).resolve([7001], user)

    assert result.matched_count == 0
    assert result.deletable == []
    assert "clients.user_id = %s" in db.statement
    assert "clients.is_active is true" in db.statement
