# -*- coding: utf-8 -*-
"""产品分配当前归属推断：结束分配后须同步 Product.client_id，避免空窗回退漏数据。"""
from datetime import date

import pytest

from app.core.product_assignment import resolve_product_current_owner


def test_resolve_owner_with_active_assignment():
    assignments = [
        (100, date(2026, 8, 1), date(2026, 8, 19)),
        (200, date(2026, 8, 20), None),
    ]
    client_id, holding_start = resolve_product_current_owner(
        assignments, holding_client_id=1
    )
    assert client_id == 200
    assert holding_start is None


def test_resolve_owner_all_ended_needs_holding_from_next_day():
    assignments = [
        (1042, date(2026, 8, 7), date(2026, 8, 19)),
    ]
    client_id, holding_start = resolve_product_current_owner(
        assignments, holding_client_id=1
    )
    assert client_id == 1
    assert holding_start == date(2026, 8, 20)


def test_resolve_owner_multiple_ended_uses_latest_end():
    assignments = [
        (1, date(2026, 8, 7), date(2026, 8, 13)),
        (1042, date(2026, 8, 14), date(2026, 8, 19)),
    ]
    client_id, holding_start = resolve_product_current_owner(
        assignments, holding_client_id=1
    )
    assert client_id == 1
    assert holding_start == date(2026, 8, 20)


def test_resolve_owner_rejects_multiple_active():
    assignments = [
        (10, date(2026, 8, 1), None),
        (20, date(2026, 8, 10), None),
    ]
    with pytest.raises(ValueError, match="当前有效分配"):
        resolve_product_current_owner(assignments, holding_client_id=1)


def test_resolve_owner_empty_assignments_holds_today():
    client_id, holding_start = resolve_product_current_owner(
        [], holding_client_id=1
    )
    assert client_id == 1
    assert holding_start == date.today()
