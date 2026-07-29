"""产品查找与创建"""
import logging
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.product_assignment import initialize_product_assignment
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
    product_result = await db.execute(product_query)
    products = product_result.unique().all()

    product_map: dict[str, dict[str, Any]] = {}
    product_name_map: dict[str, list[dict[str, Any]]] = {}

    for product, client in products:
        key = f"{client.id}_{product.name}"
        product_info = {
            "product_id": product.id,
            "client_id": client.id,
            "client_name": client.company_name,
            "product_name": product.name,
            "ecpm_deduct_ratio": product.ecpm_deduct_ratio,
            "revenue_deduct_ratio": product.revenue_deduct_ratio
        }
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

    # 首先尝试按产品名称查找
    matches = product_name_map.get(product_name, [])

    # ---------- 条件分支 ----------
    if len(matches) > 0:
        # 规则1.1：产品名称能找到客户
        # ---------- 条件分支 ----------
        if len(matches) == 1:
            product_info = matches[0]
            target_client_id = product_info["client_id"]
            logger.info(
                f"✅ 产品名称'{product_name}'找到客户，"
                f"使用产品ID: {product_info['product_id']}，客户ID: {target_client_id}"
            )
        else:
            # 多个匹配，优先使用指定客户ID的产品
            # ---------- 条件分支 ----------
            if target_client_id:
                matched_product = next(
                    (m for m in matches if m["client_id"] == target_client_id), None
                )
                # ---------- 条件分支 ----------
                if matched_product:
                    product_info = matched_product
                    logger.info(
                        f"✅ 产品名称'{product_name}'在客户ID {target_client_id} 中找到匹配"
                    )
                else:
                    product_info = matches[0]
                    target_client_id = product_info["client_id"]
                    client_list = [
                        f"客户ID {m['client_id']} ({m['client_name']})" for m in matches
                    ]
                    logger.warning(
                        f"产品名称'{product_name}'对应多个客户: {', '.join(client_list)}。"
                        f"使用第一个匹配的产品（客户ID: {target_client_id}）"
                    )
            else:
                product_info = matches[0]
                target_client_id = product_info["client_id"]
                client_list = [
                    f"客户ID {m['client_id']} ({m['client_name']})" for m in matches
                ]
                logger.warning(
                    f"产品名称'{product_name}'对应多个客户: {', '.join(client_list)}。"
                    f"使用第一个匹配的产品（客户ID: {target_client_id}）"
                )
        return product_info
    else:
        # 规则1.2：产品名称不能找到客户
        # ---------- 条件分支 ----------
        if mapping_complete:
            logger.info(
                f"✅ 映射完整，产品名称'{product_name}'找不到客户，"
                f"将创建新产品（挂靠到临时挂靠客户）"
            )

            # 获取或创建临时挂靠客户：使用统一的辅助函数
            create_client = None
            # ---------- 条件分支 ----------
            if not target_client_id:
                create_client = await find_or_create_default_client(db, current_user.id)
                target_client_id = create_client.id
                logger.info(
                    f"使用临时挂靠客户（ID: {target_client_id}，"
                    f"客户名称: {create_client.company_name}）创建产品"
                )
            else:
                # 验证指定的客户是否存在
                client_result = await db.execute(
                    select(Client).where(Client.id == target_client_id)
                )
                create_client = client_result.scalars().first()
                # ---------- 条件分支 ----------
                if not create_client:
                    raise ValueError(f"客户ID {target_client_id} 不存在")

            # ---------- 条件分支 ----------
            if not create_client:
                client_result = await db.execute(
                    select(Client).where(Client.id == target_client_id)
                )
                create_client = client_result.scalars().first()

            # 创建新产品（扣减比例设为0，不扣减）
            # 只有在产品已存在且有扣减比例时，才使用产品的扣减比例
            new_product = Product(
                client_id=target_client_id,
                name=product_name,
                ecpm_deduct_ratio=0.0,  # 新建产品默认不扣减
                revenue_deduct_ratio=0.0,  # 新建产品默认不扣减
                is_active=True
            )
            db.add(new_product)
            await db.flush()
            await db.refresh(new_product)

            # 初始化产品分配记录（确保新创建的产品有分配记录）
            # ---------- 异常处理 ----------
            try:
                product_start_date = date.today()
                await initialize_product_assignment(
                    db=db,
                    product_id=new_product.id,
                    client_id=target_client_id,
                    start_date=product_start_date
                )
                logger.info(
                    f"✅ 产品 {new_product.id} 的分配记录已初始化：客户 {target_client_id}，开始日期: {product_start_date}"
                )
            except Exception as e:
                logger.warning(
                    f"初始化产品分配记录失败: {str(e)}，但产品创建继续。"
                    f"产品ID: {new_product.id}，客户ID: {target_client_id}"
                )
                # 分配记录初始化失败不影响产品创建，继续执行

            product_info = {
                "product_id": new_product.id,
                "client_id": target_client_id,
                "client_name": create_client.company_name,
                "product_name": product_name,
                "ecpm_deduct_ratio": 0.0,  # 新建产品默认不扣减
                "revenue_deduct_ratio": 0.0  # 新建产品默认不扣减
            }

            # 添加到映射中
            key = f"{target_client_id}_{product_name}"
            product_map[key] = product_info
            product_name_map[product_name] = [product_info]

            logger.info(
                f"✅ 已创建新产品: {product_name} "
                f"(ID: {new_product.id}, 客户ID: {target_client_id}, "
                f"客户名称: {create_client.company_name})，扣减比例设为0（不扣减），"
                f"后续可手动修改客户和扣减比例"
            )

            return product_info
        else:
            raise ValueError(
                f"字段映射不完整，无法导入数据。产品 '{product_name}' 不存在且无法自动创建。"
            )

