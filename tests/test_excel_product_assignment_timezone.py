"""Excel 产品归属日期必须使用应用配置时区。"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api_v1.excel.ad_data_import import product_resolver


@pytest.mark.asyncio
async def test_new_product_assignment_uses_application_timezone_date(monkeypatch):
    """系统时区与 APP_TIMEZONE 不一致时，产品起始归属日期仍应按业务时区计算。"""
    app_now = datetime(2026, 11, 22, 0, 30, 0)
    monkeypatch.setattr(product_resolver, "get_app_now_naive", lambda: app_now)

    client = SimpleNamespace(id=99, company_name="CI Client")
    db_result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(first=lambda: client)
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=db_result))

    saved_product = SimpleNamespace(id=123, client_id=99)
    monkeypatch.setattr(
        product_resolver, "fetch_products_by_name", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        product_resolver, "insert_unique_product",
        AsyncMock(return_value=(saved_product, True)),
    )
    initialize_assignment = AsyncMock()
    monkeypatch.setattr(
        product_resolver, "initialize_product_assignment", initialize_assignment
    )
    monkeypatch.setattr(
        product_resolver, "validate_product_assignments",
        AsyncMock(return_value={"errors": []}),
    )
    monkeypatch.setattr(
        product_resolver, "_product_info",
        lambda product, target_client: {
            "product_id": product.id,
            "client_id": target_client.id,
            "product_name": "Timezone Product",
        },
    )
    monkeypatch.setattr(product_resolver, "_remember_product", lambda *args: None)

    await product_resolver.find_or_create_product(
        product_name="Timezone Product",
        target_client_id=99,
        client_id=None,
        mapping_complete=True,
        product_map={},
        product_name_map={},
        db=db,
        current_user=SimpleNamespace(id=7),
    )

    initialize_assignment.assert_awaited_once()
    assert initialize_assignment.await_args.kwargs["start_date"] == app_now.date()
