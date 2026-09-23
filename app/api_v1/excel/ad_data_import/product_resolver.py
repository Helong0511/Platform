"""产品查找与创建"""
import logging
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.product_assignment import initialize_product_assignment
from app.core.product_name import (
    choose_product_match,
    fetch_products_by_name,
    insert_unique_product,
    normalize_product_name,
)
from app.core.utils import find_or_create_default_client
from app.models.models import User, Client, Product

logger = logging.getLogger(__name__)


async def build_product_maps(
        db: AsyncSession
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """
    构建产品映射表
        
        返回:
            (product_map, product_name_map)
    
    鉴权：由 Depends(get_current_user) 或 require_admin 控制；客户角色仅可操作自有数据。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
    product_query = select(Product, Client)
    product_query = product_query.join(Client, Product.client_id == Client.id)
    product_query = product_query.order_by(Product.id.asc())
    product_result = await db.execute(product_query)
    products = product_result.unique().all()

    product_map: dict[str, dict[str, Any]] = {}
    product_name_map: dict[str, list[dict[str, Any]]] = {}

    for product, client in products:
        key = f"{client.id}_{product.name}"
        product_info = _product_info(product, client)
        product_map[key] = product_info

        if product.name not in product_name_map:
            product_name_map[product.name] = []
        product_name_map[product.name].append(product_info)

    return product_map, product_name_map


async def find_or_create_product(
        product_name: str,
        target_client_id: int | None,
        client_id: int | None,
        mapping_complete: bool,
        product_map: dict[str, dict[str, Any]],
        product_name_map: dict[str, list[dict[str, Any]]],
        db: AsyncSession,
        current_user: User
) -> dict[str, Any]:
    """
    查找或创建产品
        
        返回:
            产品信息字典
    
    鉴权：由 Depends(get_current_user) 或 require_admin 控制；客户角色仅可操作自有数据。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 确定目标客户ID（查询参数优先）
    target_client_id = client_id or target_client_id
    product_name = normalize_product_name(product_name)
    if not product_name:
        raise ValueError("产品名称不能为空")

    # 首先尝试按产品名称查找（同名多条时固定用最小 ID，不再新建）
    product_info = choose_product_match(
        product_name_map.get(product_name, []),
        target_client_id,
    )
    if product_info is not None:
        logger.info(
            "✅ 产品名称'%s'使用产品ID: %s，客户ID: %s",
            product_name,
            product_info["product_id"],
            product_info["client_id"],
        )
        return product_info

    # 内存名单是任务开始时的快照，创建前再查一次库（不加行锁，避免先于名称锁）
    existing_rows = await fetch_products_by_name(db, product_name, lock=False)
    if existing_rows:
        product_info = await _product_info_for(db, existing_rows[0])
        _remember_product(product_map, product_name_map, product_info)
        logger.info(
            "✅ 产品名称'%s'已在库中，使用产品ID: %s",
            product_name,
            product_info["product_id"],
        )
        return product_info

    if not mapping_complete:
        raise ValueError(
            f"字段映射不完整，无法导入数据。产品 '{product_name}' 不存在且无法自动创建。"
        )

    logger.info(
        "✅ 映射完整，产品名称'%s'找不到客户，将创建新产品（挂靠到临时挂靠客户）",
        product_name,
    )

    create_client = None
    if not target_client_id:
        create_client = await find_or_create_default_client(db, current_user.id)
        target_client_id = create_client.id
        logger.info(
            "使用临时挂靠客户（ID: %s，客户名称: %s）创建产品",
            target_client_id,
            create_client.company_name,
        )
    else:
        client_result = await db.execute(
            select(Client).where(Client.id == target_client_id)
        )
        create_client = client_result.scalars().first()
        if not create_client:
            raise ValueError(f"客户ID {target_client_id} 不存在")

    new_product = Product(
        client_id=target_client_id,
        name=product_name,
        ecpm_deduct_ratio=0.0,
        revenue_deduct_ratio=0.0,
        is_active=True,
    )
    saved_product, created = await insert_unique_product(db, new_product)
    if not created:
        product_info = await _product_info_for(db, saved_product)
        _remember_product(product_map, product_name_map, product_info)
        return product_info

    try:
        product_start_date = date.today()
        await initialize_product_assignment(
            db=db,
            product_id=saved_product.id,
            client_id=saved_product.client_id,
            start_date=product_start_date,
        )
        logger.info(
            "✅ 产品 %s 的分配记录已初始化：客户 %s，开始日期: %s",
            saved_product.id,
            saved_product.client_id,
            product_start_date,
        )
    except Exception as e:
        logger.warning(
            "初始化产品分配记录失败: %s，但产品创建继续。产品ID: %s，客户ID: %s",
            e,
            saved_product.id,
            saved_product.client_id,
        )

    product_info = _product_info(saved_product, create_client)
    _remember_product(product_map, product_name_map, product_info)
    logger.info(
        "✅ 已创建新产品: %s (ID: %s, 客户ID: %s, 客户名称: %s)，扣减比例设为0",
        product_name,
        saved_product.id,
        saved_product.client_id,
        create_client.company_name,
    )
    return product_info


def _product_info(product: Product, client: Client) -> dict[str, Any]:
    return {
        "product_id": product.id,
        "client_id": client.id,
        "client_name": client.company_name,
        "product_name": product.name,
        "ecpm_deduct_ratio": product.ecpm_deduct_ratio,
        "revenue_deduct_ratio": product.revenue_deduct_ratio,
    }


async def _product_info_for(db: AsyncSession, product: Product) -> dict[str, Any]:
    client_result = await db.execute(select(Client).where(Client.id == product.client_id))
    client = client_result.scalar_one()
    return _product_info(product, client)


def _remember_product(
        product_map: dict[str, dict[str, Any]],
        product_name_map: dict[str, list[dict[str, Any]]],
        product_info: dict[str, Any],
) -> None:
    key = f"{product_info['client_id']}_{product_info['product_name']}"
    product_map[key] = product_info
    product_name_map[product_info["product_name"]] = [product_info]

