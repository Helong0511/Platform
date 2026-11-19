"""高流量列表统一分页 OFFSET 预算回归测试。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api_v1.tb_search_data import get_tb_search_data
from app.core.pagination import calculate_pagination_offset, paginate_query
from app.models.models import User, UserRole
from app.services.click_service import ClickService
from app.services.cpl.postback_forward_log_service import PostbackForwardLogService
from app.services.cpl.postback_pending_service import PostbackPendingService
from app.services.short_link_service import ShortLinkService


class _NoDB:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        raise AssertionError("pagination budget must reject before database access")


def _admin():
    return SimpleNamespace(id=1, role=UserRole.ADMIN)


def test_calculate_pagination_offset_allows_exact_boundary():
    assert calculate_pagination_offset(1001, 100) == 100000
    assert calculate_pagination_offset(
        101,
        1000,
        max_page_size=1000,
    ) == 100000


@pytest.mark.parametrize(
    ("page", "page_size", "kwargs"),
    [
        (1002, 100, {}),
        (102, 1000, {"max_page_size": 1000}),
        (0, 10, {}),
        (True, 10, {}),
        (1, 101, {}),
    ],
)
def test_calculate_pagination_offset_rejects_invalid_or_excessive_values(
    page,
    page_size,
    kwargs,
):
    with pytest.raises(HTTPException):
        calculate_pagination_offset(page, page_size, **kwargs)


@pytest.mark.asyncio
async def test_generic_paginate_query_rejects_before_count_query():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await paginate_query(
            db=db,
            query=select(User),
            page=1002,
            page_size=100,
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_click_list_rejects_deep_offset_before_database():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await ClickService(db).get_clicks(page=1002, page_size=100)

    assert db.statements == []


@pytest.mark.asyncio
async def test_postback_forward_log_list_rejects_deep_offset_before_database():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await PostbackForwardLogService().list_forward_logs(
            conversion_id=None,
            product_id=None,
            publisher_id=None,
            success=None,
            start_date=None,
            end_date=None,
            page=102,
            page_size=1000,
            db=db,
            current_user=_admin(),
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_pending_postback_list_rejects_deep_offset_before_database():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await PostbackPendingService().get_pending_postback_conversions(
            platform=None,
            request_ip=None,
            status=None,
            start_date=None,
            end_date=None,
            page=102,
            page_size=1000,
            db=db,
            current_user=_admin(),
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_short_link_list_rejects_deep_offset_before_database():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await ShortLinkService(db).get_short_links(
            current_user=_admin(),
            page=1002,
            page_size=100,
        )

    assert db.statements == []


@pytest.mark.asyncio
async def test_tb_search_list_rejects_deep_offset_before_database():
    db = _NoDB()

    with pytest.raises(HTTPException):
        await get_tb_search_data(
            request=SimpleNamespace(headers={}),
            db=db,
            current_user=_admin(),
            page=1002,
            page_size=100,
        )

    assert db.statements == []
