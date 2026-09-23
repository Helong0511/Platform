"""产品名称全局唯一。

入库与管理端创建都先按名称查库。已有同名产品时复用 ID 最小的一条，不再插入。
并发插入靠唯一索引 uq_products_name：后到的一方收到重复键后改读已有产品。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import Product

logger = logging.getLogger(__name__)

_WARNED_DUPLICATE_NAMES: set[str] = set()


def normalize_product_name(name: str | None) -> str:
    """去掉首尾空白。空名称由调用方拒绝。"""
    return str(name or "").strip()


def duplicate_name_detail(name: str, products: list[Product]) -> str:
    """管理端拒绝重名时的说明。"""
    ids = "、".join(str(product.id) for product in products)
    if len(products) > 1:
        return (
            f"产品名称「{name}」已存在 {len(products)} 条（产品ID: {ids}），"
            "不能重复创建。请先处理已有重复产品。"
        )
    product_id = products[0].id if products else "?"
    return f"产品名称「{name}」已存在（产品ID: {product_id}），不能重复创建。"


def choose_product_match(
        matches: list[dict[str, Any]],
        target_client_id: int | None,
) -> dict[str, Any] | None:
    """同名有多条时，优先指定客户里 ID 最小的一条，否则用全局最小 ID。"""
    if not matches:
        return None
    ordered = sorted(matches, key=lambda item: item["product_id"])
    if len(ordered) == 1:
        return ordered[0]

    chosen = ordered[0]
    if target_client_id is not None:
        for item in ordered:
            if item["client_id"] == target_client_id:
                chosen = item
                break

    name = str(chosen.get("product_name") or "")
    if name not in _WARNED_DUPLICATE_NAMES:
        _WARNED_DUPLICATE_NAMES.add(name)
        logger.warning(
            "产品名称「%s」对应 %s 个产品，使用产品 ID %s，不再新建",
            name,
            len(ordered),
            chosen["product_id"],
        )
    return chosen


def is_duplicate_product_name_error(exc: BaseException) -> bool:
    """MySQL 1062：产品名称唯一索引冲突。"""
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ()) or ()
    if args and args[0] == 1062:
        return True
    text_value = str(exc).lower()
    return "duplicate" in text_value and "name" in text_value


async def fetch_products_by_name(
        db: AsyncSession,
        name: str,
        *,
        lock: bool = False,
) -> list[Product]:
    """按名称取产品，ID 升序。lock=True 时读最新已提交行。"""
    stmt = select(Product).where(Product.name == name).order_by(Product.id.asc())
    if lock:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def insert_unique_product(
        db: AsyncSession,
        product: Product,
) -> tuple[Product, bool]:
    """插入产品。名称已存在时返回最小 ID 的那条，created 为 False。"""
    name = normalize_product_name(product.name)
    if not name:
        raise ValueError("产品名称不能为空")
    product.name = name

    existing = await fetch_products_by_name(db, name, lock=True)
    if existing:
        if len(existing) > 1 and name not in _WARNED_DUPLICATE_NAMES:
            _WARNED_DUPLICATE_NAMES.add(name)
            logger.warning(
                "产品名称「%s」已有 %s 条（ID: %s），复用 %s",
                name,
                len(existing),
                [item.id for item in existing],
                existing[0].id,
            )
        return existing[0], False

    try:
        async with db.begin_nested():
            db.add(product)
            await db.flush()
            await db.refresh(product)
        return product, True
    except IntegrityError as exc:
        if not is_duplicate_product_name_error(exc):
            raise
        existing = await fetch_products_by_name(db, name, lock=True)
        if not existing:
            raise
        logger.warning("并发创建撞上已有产品名称「%s」，复用产品 ID %s", name, existing[0].id)
        return existing[0], False
