# -*- coding: utf-8 -*-
"""核对脚本 fetch_db_rows 与客户 API 归属口径一致。"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_RECON_MOD = ROOT / "tests" / "每日自动报表" / "client_data_reconciliation.py"


def _load_reconciliation_module():
    spec = importlib.util.spec_from_file_location(
        "client_data_reconciliation", _RECON_MOD
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_fetch_db_rows_uses_resolved_client_scope():
    """空窗日应回退 products.client_id，不能只 EXISTS 分配表。"""
    mod = _load_reconciliation_module()
    src = inspect.getsource(mod.fetch_db_rows)
    assert "COALESCE(pa.client_id, p.client_id)" in src
    assert "LEFT JOIN product_assignments pa" in src
    assert "ORDER BY pa2.id ASC" in src
    assert "EXISTS (" not in src
