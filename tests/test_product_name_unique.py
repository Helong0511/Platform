"""产品名称全局唯一：选中规则与模型约束。"""
from sqlalchemy.exc import IntegrityError

from app.core.product_name import (
    choose_product_match,
    duplicate_name_detail,
    is_duplicate_product_name_error,
    normalize_product_name,
)
from app.models.client_product import Product


def test_product_name_unique_constraint():
    names = {constraint.name for constraint in Product.__table__.constraints}
    assert "uq_products_name" in names
    unique = next(
        constraint for constraint in Product.__table__.constraints
        if constraint.name == "uq_products_name"
    )
    assert [column.name for column in unique.columns] == ["name"]


def test_choose_single_match():
    chosen = choose_product_match(
        [{"product_id": 9, "client_id": 1, "product_name": "a"}],
        None,
    )
    assert chosen["product_id"] == 9


def test_choose_lowest_id_when_no_client():
    chosen = choose_product_match(
        [
            {"product_id": 331, "client_id": 1, "product_name": "https://news.viralposts.ng"},
            {"product_id": 329, "client_id": 1, "product_name": "https://news.viralposts.ng"},
        ],
        None,
    )
    assert chosen["product_id"] == 329


def test_choose_lowest_id_of_target_client():
    chosen = choose_product_match(
        [
            {"product_id": 40, "client_id": 2, "product_name": "same"},
            {"product_id": 12, "client_id": 8, "product_name": "same"},
            {"product_id": 30, "client_id": 8, "product_name": "same"},
        ],
        8,
    )
    assert chosen["product_id"] == 12


def test_choose_falls_back_when_client_missing():
    chosen = choose_product_match(
        [
            {"product_id": 5, "client_id": 1, "product_name": "same"},
            {"product_id": 3, "client_id": 1, "product_name": "same"},
        ],
        99,
    )
    assert chosen["product_id"] == 3


def test_normalize_and_duplicate_detail():
    assert normalize_product_name("  abc  ") == "abc"
    detail = duplicate_name_detail("abc", [type("P", (), {"id": 329})(), type("P", (), {"id": 331})()])
    assert "329" in detail and "331" in detail and "不能重复创建" in detail


def test_duplicate_key_error_detected():
    class Orig(Exception):
        def __init__(self):
            self.args = (1062, "Duplicate entry 'x' for key 'uq_products_name'")

    exc = IntegrityError("INSERT", {}, Orig())
    assert is_duplicate_product_name_error(exc)
    assert not is_duplicate_product_name_error(ValueError("other"))
