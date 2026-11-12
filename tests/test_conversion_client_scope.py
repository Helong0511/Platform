"""客户账号缺少 Client/Publisher 关联时不得退化为全局转化查询。"""
from types import SimpleNamespace

import pytest

from app.models.models import UserRole
from app.services.cpl.conversion_service import ConversionService


class MissingClientResult:
    def scalars(self):
        return self

    def all(self):
        return []


class MissingClientDB:
    def __init__(self):
        self.execute_count = 0

    async def execute(self, statement):
        self.execute_count += 1
        return MissingClientResult()


@pytest.mark.asyncio
async def test_conversion_summary_returns_empty_scope_when_client_record_missing():
    db = MissingClientDB()
    service = ConversionService(db)
    client_user = SimpleNamespace(id=902, role=UserRole.CLIENT)

    result = await service.get_conversion_summary(current_user=client_user)

    assert result["total_clicks"] == 0
    assert result["total_conversions"] == 0
    assert result["stats_list"] == []
    assert db.execute_count == 1


@pytest.mark.asyncio
async def test_conversion_by_offer_returns_empty_scope_when_client_record_missing():
    db = MissingClientDB()
    service = ConversionService(db)
    client_user = SimpleNamespace(id=903, role=UserRole.CLIENT)

    result = await service.get_conversions_by_offer(current_user=client_user)

    assert result == []
    assert db.execute_count == 1


class MultiClientDB:
    def __init__(self):
        self.execute_count = 0
        self.sql = []

    async def execute(self, statement):
        from sqlalchemy.dialects import mysql

        self.execute_count += 1
        self.sql.append(str(statement.compile(dialect=mysql.dialect())).lower())
        if self.execute_count == 1:
            return _Rows([101, 202])
        return _Rows([])


class _Rows:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


@pytest.mark.asyncio
async def test_conversion_summary_collects_all_client_records_before_scoping_publishers():
    db = MultiClientDB()
    service = ConversionService(db)
    client_user = SimpleNamespace(id=904, role=UserRole.CLIENT)

    result = await service.get_conversion_summary(current_user=client_user)

    assert result["total_clicks"] == 0
    assert result["stats_list"] == []
    assert db.execute_count == 2
    assert "clients.user_id = %s" in db.sql[0]
    assert "clients.is_active is true" in db.sql[0]
    assert " limit " not in db.sql[0]
    assert "publishers.client_id in" in db.sql[1]
    assert "publishers.is_active = true" in db.sql[1]


@pytest.mark.asyncio
async def test_conversion_by_offer_collects_all_client_records_before_scoping_publishers():
    db = MultiClientDB()
    service = ConversionService(db)
    client_user = SimpleNamespace(id=905, role=UserRole.CLIENT)

    result = await service.get_conversions_by_offer(current_user=client_user)

    assert result == []
    assert db.execute_count == 2
    assert "clients.user_id = %s" in db.sql[0]
    assert "clients.is_active is true" in db.sql[0]
    assert " limit " not in db.sql[0]
    assert "publishers.client_id in" in db.sql[1]
    assert "publishers.is_active is true" in db.sql[1]
