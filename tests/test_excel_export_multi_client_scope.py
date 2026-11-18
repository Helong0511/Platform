"""Excel 导出必须覆盖用户全部启用 Client，不能依赖数据库返回的第一条记录。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api_v1.excel import export_handler
from app.models.models import UserRole


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DB:
    def __init__(self, active_client_id):
        self.active_client_id = active_client_id
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _ScalarResult(self.active_client_id)


def _client_user():
    return SimpleNamespace(id=701, username="multi-client", role=UserRole.CLIENT)


@pytest.mark.asyncio
async def test_daily_summary_export_does_not_pin_multi_client_user_to_first_client(monkeypatch):
    db = _DB(active_client_id=11)
    captured = {}

    async def fake_export_daily_summary(**kwargs):
        captured.update(kwargs)
        return "stream-response"

    monkeypatch.setattr(
        export_handler,
        "_export_daily_summary_excel",
        fake_export_daily_summary,
    )

    response = await export_handler.export_ad_data_handler(
        db=db,
        current_user=_client_user(),
        daily_summary=True,
    )

    assert response == "stream-response"
    # None 表示交由 DailySummaryQuery 的服务端用户范围过滤全部启用 Client。
    assert captured["target_client_id"] is None
    sql = str(db.statements[0])
    assert "clients.user_id" in sql
    assert "clients.is_active" in sql


@pytest.mark.asyncio
async def test_export_rejects_user_without_any_active_client(monkeypatch):
    db = _DB(active_client_id=None)

    async def unexpected_export(**kwargs):
        pytest.fail("没有启用 Client 时不应进入导出查询")

    monkeypatch.setattr(
        export_handler,
        "_export_daily_summary_excel",
        unexpected_export,
    )

    with pytest.raises(HTTPException) as caught:
        await export_handler.export_ad_data_handler(
            db=db,
            current_user=_client_user(),
            daily_summary=True,
        )

    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_detail_export_passes_unrestricted_client_filter_to_user_scope(monkeypatch):
    """明细导出应把 None 交给统一范围过滤器，而非传入字符串 'None'。"""
    db = _DB(active_client_id=11)
    captured = {}

    class _StopAfterScope(Exception):
        pass

    async def capture_scope(*args, **kwargs):
        captured.update(kwargs)
        raise _StopAfterScope

    monkeypatch.setattr(export_handler, "check_use_assignment_table", lambda _db: _false())
    monkeypatch.setattr(export_handler, "apply_ad_data_scope_filters", capture_scope)

    async def _false():
        return False

    with pytest.raises(_StopAfterScope):
        await export_handler.export_ad_data_handler(
            db=db,
            current_user=_client_user(),
            daily_summary=False,
        )

    assert captured["client_id"] is None
    assert captured["current_user"].id == 701
