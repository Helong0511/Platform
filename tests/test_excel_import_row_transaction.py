"""Excel 导入逐行事务边界回归测试。"""
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from app.api_v1.excel.ad_data_import import row_processor


class _Savepoint:
    def __init__(self):
        self.is_active = True
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True
        self.is_active = False

    async def rollback(self):
        self.rolled_back = True
        self.is_active = False


class _DB:
    def __init__(self):
        self.savepoint = _Savepoint()
        self.begin_nested_calls = 0

    async def begin_nested(self):
        self.begin_nested_calls += 1
        return self.savepoint


@pytest.mark.asyncio
async def test_invalid_metrics_roll_back_new_product_side_effects_and_cache(monkeypatch):
    db = _DB()
    product_map = {"1_old": {"product_id": 1, "product_name": "old"}}
    product_name_map = {"old": [{"product_id": 1, "product_name": "old"}]}
    existing_records = {}
    result = {
        "success_rows": 0,
        "failed_rows": 0,
        "new_rows": 0,
        "updated_rows": 0,
        "errors": [],
    }

    async def fake_find_or_create_product(**kwargs):
        # 模拟解析器已创建产品并更新了当前批次缓存。
        kwargs["product_map"]["2_new"] = {
            "product_id": 2,
            "client_id": 2,
            "product_name": "new",
        }
        kwargs["product_name_map"]["new"] = [{
            "product_id": 2,
            "client_id": 2,
            "product_name": "new",
        }]
        return {
            "product_id": 2,
            "client_id": 2,
            "product_name": "new",
            "ecpm_deduct_ratio": 0.0,
            "revenue_deduct_ratio": 0.0,
        }

    monkeypatch.setattr(
        row_processor, "find_or_create_product", fake_find_or_create_product
    )
    row = pd.Series({
        "date": datetime(2026, 11, 17),
        "product_name": "new",
        "request_count": "not-a-number",
        "match_count": 0,
        "display_count": 0,
        "click_count": 0,
        "revenue_before_deduct": 0,
    })

    await row_processor.process_row_data(
        row=row,
        row_num=2,
        product_map=product_map,
        product_name_map=product_name_map,
        mapping_complete=True,
        client_id=None,
        db=db,
        current_user=SimpleNamespace(username="test"),
        result=result,
        existing_records=existing_records,
    )

    assert db.begin_nested_calls == 1
    assert db.savepoint.rolled_back is True
    assert db.savepoint.committed is False
    assert "2_new" not in product_map
    assert "new" not in product_name_map
    assert set(product_map) == {"1_old"}
    assert result["success_rows"] == 0
    assert result["failed_rows"] == 1
    assert result["new_rows"] == 0
    assert result["updated_rows"] == 0
    assert result["errors"][0]["row"] == 2
    assert "数值字段格式错误" in result["errors"][0]["error"]


@pytest.mark.asyncio
async def test_assignment_initialization_error_is_counted_as_failed_row_and_rolled_back(
    monkeypatch,
):
    db = _DB()
    product_map = {}
    product_name_map = {}
    result = {
        "success_rows": 0,
        "failed_rows": 0,
        "new_rows": 0,
        "updated_rows": 0,
        "errors": [],
    }

    async def fake_find_or_create_product(**kwargs):
        # 模拟 Product 已插入，随后初始 ProductAssignment 创建失败。
        kwargs["product_map"]["3_broken"] = {"product_id": 3}
        raise RuntimeError("初始产品归属记录创建失败")

    monkeypatch.setattr(
        row_processor, "find_or_create_product", fake_find_or_create_product
    )
    row = pd.Series({
        "date": datetime(2026, 11, 17),
        "product_name": "broken",
    })

    await row_processor.process_row_data(
        row=row,
        row_num=3,
        product_map=product_map,
        product_name_map=product_name_map,
        mapping_complete=True,
        client_id=3,
        db=db,
        current_user=SimpleNamespace(username="test"),
        result=result,
        existing_records={},
    )

    assert db.savepoint.rolled_back is True
    assert db.savepoint.committed is False
    assert product_map == {}
    assert product_name_map == {}
    assert result["success_rows"] == 0
    assert result["failed_rows"] == 1
    assert "初始产品归属记录创建失败" in result["errors"][0]["error"]
