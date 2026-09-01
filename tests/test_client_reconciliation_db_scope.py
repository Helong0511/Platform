# -*- coding: utf-8 -*-
"""
客户核对 fetch_db_rows 与客户 API 归属口径一致。

真源在 app（已提交）：join_helpers.resolved_client_id_expr /
outerjoin_best_product_assignment、client_api_query._apply_client_product_scope。

tests/每日自动报表/client_data_reconciliation.py 被 .gitignore 忽略，
CI/新克隆可能没有该脚本，因此不得依赖动态加载该文件。
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

from app.models.models import AdData
from app.services.ad_data.queries.client_api_query import ClientAdDataQuery
from app.services.ad_data.queries.join_helpers import (
    best_product_assignment_id_subquery,
    outerjoin_best_product_assignment,
    resolved_client_id_expr,
)

ROOT = Path(__file__).resolve().parents[1]
_LOCAL_RECON_MOD = ROOT / "tests" / "每日自动报表" / "client_data_reconciliation.py"


def test_resolved_client_id_coalesce_assignment_or_product():
    """空窗日应回退 products.client_id。"""
    compiled = str(
        resolved_client_id_expr().compile(compile_kwargs={"literal_binds": False})
    )
    assert "coalesce" in compiled.lower()


def test_best_assignment_picks_min_id_for_product_date():
    """按 (product, date) 取最小 id 的一条分配。"""
    subq = best_product_assignment_id_subquery(AdData.date)
    compiled = str(subq.compile(compile_kwargs={"literal_binds": False}))
    lower = compiled.lower()
    assert "product_assignments" in lower
    assert "order by" in lower and "id" in lower
    assert "limit" in lower


def test_client_api_uses_resolved_client_scope_not_exists_only():
    """客户 API 须 outerjoin + COALESCE，不能仅 EXISTS 分配表。"""
    src = inspect.getsource(ClientAdDataQuery._apply_client_product_scope)
    assert "outerjoin_best_product_assignment" in src
    assert "resolved_client_id_expr" in src
    assert "EXISTS (" not in src


def test_outerjoin_best_assignment_uses_left_join_semantics():
    src = inspect.getsource(outerjoin_best_product_assignment)
    assert "outerjoin" in src.lower()


@pytest.mark.skipif(
    not _LOCAL_RECON_MOD.is_file(),
    reason="本地核对脚本未检出（tests/* 默认 gitignore，CI 不依赖）",
)
def test_local_reconciliation_script_aligns_when_present():
    """若本机存在核对脚本，其 fetch_db_rows 应与 app 口径一致。"""
    spec = importlib.util.spec_from_file_location(
        "client_data_reconciliation", _LOCAL_RECON_MOD
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = inspect.getsource(mod.fetch_db_rows)
    assert "COALESCE(pa.client_id, p.client_id)" in src
    assert "LEFT JOIN product_assignments pa" in src
    assert "ORDER BY pa2.id ASC" in src
    assert "EXISTS (" not in src
