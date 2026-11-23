"""Excel 导出异常响应不得泄露数据库或内部驱动细节。"""
import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

excel_router = importlib.import_module("app.api_v1.excel.router")


@pytest.mark.asyncio
async def test_export_error_response_redacts_internal_exception(monkeypatch):
    secret_detail = "mysql://internal-db.local:3306/platform password=top-secret"

    async def fail_export(**_kwargs):
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(excel_router, "export_ad_data_handler", fail_export)

    with pytest.raises(HTTPException) as caught:
        await excel_router.export_ad_data(
            request=SimpleNamespace(),
            start_date=None,
            end_date=None,
            product_id=None,
            client_id=None,
            country_code=None,
            ad_unit=None,
            dimension="country",
            data_source=None,
            upstream_account=None,
            report_type=None,
            daily_summary=False,
            split_by_country=False,
            sort_by="date",
            sort_order="desc",
            db=SimpleNamespace(),
            current_user=SimpleNamespace(id=1),
        )

    assert secret_detail not in str(caught.value.detail)
    assert "导出数据失败，请稍后重试" in str(caught.value.detail)
