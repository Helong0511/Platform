"""报表 API 的内部异常信息脱敏回归测试。"""
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api_v1 import dashboard as dashboard_api
from app.api_v1.cpl.conversions import summary as conversion_summary_api
from app.models.models import UserRole
from app.services.dashboard_service import DashboardService


PRIVATE_ERROR = "private@example.invalid click_id=private-click-id ip=203.0.113.77"


@pytest.mark.asyncio
async def test_dashboard_stats_does_not_return_or_log_raw_exception(monkeypatch, caplog):
    class BrokenService:
        async def get_dashboard_stats(self, **kwargs):
            raise RuntimeError(PRIVATE_ERROR)

    async def get_service(db):
        return BrokenService()

    monkeypatch.setattr(dashboard_api, "get_dashboard_service", get_service)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as caught:
            await dashboard_api.get_dashboard_stats(
                period="week",
                db=object(),
                current_user=SimpleNamespace(id=1, role=UserRole.ADMIN),
            )

    assert PRIVATE_ERROR not in str(caught.value.detail)
    assert PRIVATE_ERROR not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_dashboard_trends_does_not_return_or_log_raw_exception(monkeypatch, caplog):
    class BrokenService:
        async def get_trend_data(self, **kwargs):
            raise RuntimeError(PRIVATE_ERROR)

    async def get_service(db):
        return BrokenService()

    monkeypatch.setattr(dashboard_api, "get_dashboard_service", get_service)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as caught:
            await dashboard_api.get_trend_data(
                period="week",
                db=object(),
                current_user=SimpleNamespace(id=1, role=UserRole.ADMIN),
            )

    assert PRIVATE_ERROR not in str(caught.value.detail)
    assert PRIVATE_ERROR not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_recent_dashboard_service_logs_only_exception_type(monkeypatch, caplog):
    async def fail_assignment_check(db):
        raise RuntimeError(PRIVATE_ERROR)

    monkeypatch.setattr(
        "app.services.dashboard_service.check_use_assignment_table",
        fail_assignment_check,
    )
    service = DashboardService(object())

    with caplog.at_level(logging.ERROR):
        result = await service.get_recent_ad_data(
            current_user=SimpleNamespace(id=1, role=UserRole.CLIENT),
            days=7,
        )

    assert result["ads"] == []
    assert PRIVATE_ERROR not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_conversion_summary_does_not_return_or_log_raw_exception(monkeypatch, caplog):
    class BrokenService:
        async def get_conversion_summary(self, **kwargs):
            raise RuntimeError(PRIVATE_ERROR)

    async def get_service(db):
        return BrokenService()

    monkeypatch.setattr(conversion_summary_api, "get_conversion_service", get_service)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as caught:
            await conversion_summary_api.get_conversion_summary(
                db=object(),
                current_user=SimpleNamespace(id=1, role=UserRole.ADMIN),
            )

    assert PRIVATE_ERROR not in str(caught.value.detail)
    assert PRIVATE_ERROR not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_conversion_by_offer_does_not_return_or_log_raw_exception(monkeypatch, caplog):
    class BrokenService:
        async def get_conversions_by_offer(self, **kwargs):
            raise RuntimeError(PRIVATE_ERROR)

    async def get_service(db):
        return BrokenService()

    monkeypatch.setattr(conversion_summary_api, "get_conversion_service", get_service)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as caught:
            await conversion_summary_api.get_summary_by_offer(
                db=object(),
                current_user=SimpleNamespace(id=1, role=UserRole.ADMIN),
            )

    assert PRIVATE_ERROR not in str(caught.value.detail)
    assert PRIVATE_ERROR not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_recent_dashboard_route_logs_only_exception_type(monkeypatch, caplog):
    class BrokenService:
        async def get_recent_ad_data(self, **kwargs):
            raise RuntimeError(PRIVATE_ERROR)

    async def get_service(db):
        return BrokenService()

    monkeypatch.setattr(dashboard_api, "get_dashboard_service", get_service)
    with caplog.at_level(logging.ERROR):
        await dashboard_api.get_recent_ad_data(
            db=object(),
            current_user=SimpleNamespace(id=1, role=UserRole.ADMIN),
        )

    assert PRIVATE_ERROR not in caplog.text
    assert "RuntimeError" in caplog.text
