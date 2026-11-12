"""客户账号缺少 Client/Publisher 关联时不得退化为全局转化查询。"""
from types import SimpleNamespace

import pytest

from app.models.models import UserRole
from app.services.cpl.conversion_service import ConversionService


class MissingClientResult:
    def scalar_one_or_none(self):
        return None


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
