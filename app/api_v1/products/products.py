"""产品管理API端点模块

功能说明：
提供产品信息的完整CRUD操作，包括：
- 可用产品列表：获取可用于创建产品的产品名称列表
- 产品列表查询：支持分页、筛选、搜索
- 产品详情查询：根据ID获取产品详细信息
- 产品创建：创建新产品（验证客户权限和唯一性）
- 产品更新：更新产品信息（包括客户转移）
- 产品删除：删除产品（检查关联广告数据）
- 产品激活/禁用：激活或禁用产品

权限控制：
- 管理员：可以管理所有产品
- 客户：只能管理自己客户下的产品
- 产品查看：根据产品分配历史判断权限

功能特性：
1. 可用产品列表：
   - 返回关联管理员的客户的产品和其他客户的产品
   - 排除当前客户已有的产品（避免重复）
   - 支持搜索过滤
   - 用于产品创建时的选择

2. 产品列表查询：
   - 支持按客户、状态筛选
   - 支持全文搜索（产品名称）
   - 根据设备类型自动优化分页大小
   - 返回标准分页响应格式

3. 产品创建：
   - 验证产品名称唯一性（同一客户下）
   - 验证客户权限（客户只能创建自己客户下的产品）
   - 自动初始化产品分配历史
   - 记录审计日志

4. 产品更新：
   - 验证产品名称唯一性（如果修改）
   - 支持客户转移（自动处理产品分配历史）
   - 支持更新Postback URL和通知配置
   - 记录审计日志

5. 产品删除：
   - 检查是否有关联的广告数据
   - 如果有关联数据，不允许删除
   - 自动关闭产品分配历史
   - 记录审计日志

6. 产品分配历史：
   - 自动管理产品分配历史
   - 支持产品在不同客户间转移
   - 记录分配开始和结束时间

使用场景：
- 管理员管理产品
- 客户管理自己的产品
- 产品在不同客户间转移
- 产品数据统计和分析

注意事项：
1. 产品名称在同一客户下必须唯一
2. 删除产品前必须检查关联的广告数据
3. 产品转移会自动处理分配历史
4. Postback URL支持占位符变量
5. 所有操作都记录审计日志。

说明：REST API 端点，统一 ResponseBaseSchema 响应；鉴权由各端点 Depends 声明。"""
# 标准库导入
import logging
import uuid

# 第三方库导入
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# 本地导入
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.audit_log import log_create, log_update, log_delete, log_activate, log_deactivate, commit_audit_log
from app.core.validation import sanitize_input
from app.core.constants import MAX_PAGE_SIZE
from app.core.utils import optimize_page_size_for_device
from app.core.fulltext_search import search_with_fulltext
from app.core.dependencies import get_product_service
from app.services.product_service import ProductService
from app.core.product_assignment import (
    transfer_product_assignment,
    initialize_product_assignment,
    close_active_assignment
)
from app.models.models import AdData, Client, Product, User, UserRole
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema, ListResponseBaseSchema
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate, build_product_response
from datetime import date

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


# 用于返回的产品简要信息模型
class ProductNameOption(BaseModel):
    """
    下拉选择用的产品简要信息（id + 名称 + 归属客户）
    
    继承 BaseModel。业务数据模型，用于序列化与反序列化。
    """
    id: int
    name: str
    client_id: int
    user_full_name: str | None = None

    class Config:
        """允许从 ORM Product 构造。用于 API 请求/响应序列化与 OpenAPI 文档生成。"""
        from_attributes = True


@router.get("/available-names", response_model=ListResponseBaseSchema[list[ProductNameOption]],
            summary="获取可用的产品列表")
async def get_available_product_names(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        exclude_client_id: int | None = Query(None, description="指定客户ID（排除该客户已有的产品）"),
        search: str | None = Query(None, description="搜索关键词")
):
    """
    获取可用的产品列表（用于添加产品时选择）
    - 返回关联管理员的客户的产品和其他客户的产品
    - 排除当前客户已有的产品（避免重复）
    - 支持搜索过滤
    - 返回产品对象列表，包含id、name、client_id
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        # 1. 查找所有管理员用户和关联的客户 - 使用JOIN优化，一次性查询
        # 优化：使用JOIN一次性获取管理员用户及其关联的客户ID，减少查询次数
        admin_clients_query = select(Client.id).join(
            User, Client.user_id == User.id
        ).where(User.role == UserRole.ADMIN)
        admin_clients_result = await db.execute(admin_clients_query)
        admin_client_ids = [row[0] for row in admin_clients_result.all()]

        # 3. 构建查询：获取产品及其归属客户的用户全名
        products_query = select(
            Product,
            User.full_name.label("user_full_name"),
        ).join(Client, Product.client_id == Client.id).join(
            User, Client.user_id == User.id
        ).where(
            Product.name.isnot(None),
            Product.name != ''
        )

        # 如果指定了要排除的客户ID，排除该客户已有的所有产品（包括转移后的产品）
        # ---------- 条件分支 ----------
        if exclude_client_id:
            # 明确排除当前客户的所有产品（client_id == exclude_client_id）
            # 返回：关联管理员的客户的产品（排除当前客户的） + 其他客户的产品（排除当前客户的）
            # ---------- 条件分支 ----------
            if admin_client_ids:
                # 排除当前客户的产品，保留关联管理员的客户的产品和其他客户的产品
                products_query = products_query.where(Product.client_id != exclude_client_id)
            else:
                # 如果没有管理员客户，只返回其他客户的产品（排除当前客户）
                products_query = products_query.where(Product.client_id != exclude_client_id)
        else:
            # 如果没有指定排除客户ID，返回关联管理员的客户的产品和所有其他客户的产品
            # ---------- 条件分支 ----------
            if admin_client_ids:
                # 返回所有产品（包括管理员客户和其他客户）
                pass  # 不需要额外过滤
            else:
                # 如果没有管理员客户，返回所有产品
                pass

        # 4. 应用搜索过滤（优先使用全文搜索，回退到LIKE）
        # ---------- 条件分支 ----------
        if search and search.strip():
            cleaned_search = sanitize_input(search.strip(), max_length=100)
            # ---------- 条件分支 ----------
            if cleaned_search:
                products_query = await search_with_fulltext(
                    db=db,
                    model_class=Product,
                    search_fields=["name"],
                    search_term=cleaned_search,
                    base_query=products_query,
                    use_fulltext=True
                )

        # 5. 执行查询
        products_result = await db.execute(products_query)

        # 6. 转换为响应模型
        product_options = []
        admin_client_ids_set = set(admin_client_ids)  # 转换为set以提高查找效率
        # ---------- 循环处理 ----------
        for product, user_full_name in products_result.unique().all():
            product_options.append(ProductNameOption(
                id=product.id,
                name=product.name,
                client_id=product.client_id,
                user_full_name=user_full_name,
            ))

        # 7. 排序：优先显示关联管理员的客户的产品，然后按名称排序
        product_options.sort(key=lambda x: (
            0 if x.client_id in admin_client_ids_set else 1,  # 管理员客户的产品排前面（0 < 1）
            x.name  # 然后按名称排序
        ))

        logger.debug(f"Available products: total={len(product_options)}")

        return ListResponseBaseSchema.success(data=product_options, count=len(product_options))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting available product names: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取产品列表失败：{str(e)}。请稍后重试或联系管理员"
        )


@router.get("/", response_model=PaginatedResponseBaseSchema[list[ProductResponse]], summary="获取产品列表")
async def get_products(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        client_id: int | None = Query(None, description="客户ID过滤"),
        name: str | None = Query(None, description="产品名称过滤"),
        is_active: bool | None = Query(None, description="是否激活过滤"),
        product_id: int | None = Query(None, ge=1, description="产品ID精确过滤（跳转定位）"),
):
    """
    获取产品列表，支持分页和过滤（已重构使用服务层）
    - 管理员可查看所有产品
    - 客户只能查看自己的产品
    - 支持按客户ID、产品ID、产品名称和激活状态过滤
    - 根据设备类型自动优化分页大小
    """
    # ====== 设备类型优化：自动调整分页大小 ======
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)
    
    # 使用服务层（业务逻辑在ProductService中）
    product_service: ProductService = await get_product_service(db)
    
    # 如果提供了name参数，优先使用全文搜索
    # 注意：全文搜索需要在查询层面处理，所以这里先获取基础查询结果
    # 如果name存在，服务层会使用LIKE查询，但我们可以考虑在endpoint层优化
    products, total = await product_service.get_products(
        current_user=current_user,
        page=page,
        page_size=page_size,
        client_id=client_id,
        name=name,
        is_active=is_active,
        product_id=product_id,
        # name 已做前缀过滤；勿再与 search 条件 AND，否则列表常为空
        search=None,
    )

    # 转换为响应模型
    product_responses = [build_product_response(product) for product in products]

    return PaginatedResponseBaseSchema.success(
        data=product_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{product_id}", response_model=ResponseBaseSchema[ProductResponse], summary="获取产品详情")
async def get_product(
        product_id: int = Path(..., ge=1, description="产品ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取指定产品的详细信息（已重构使用服务层）
    - 管理员可查看所有产品
    - 客户只能查看自己的产品
    - 返回产品完整信息，包括减扣比例
    - 使用服务层，业务逻辑已优化
    """
    # 使用服务层（业务逻辑在ProductService中）
    product_service: ProductService = await get_product_service(db)
    product = await product_service.get_product_by_id(product_id, current_user, include_client=True)

    return ResponseBaseSchema.success(data=build_product_response(product))


@router.post("/", response_model=ResponseBaseSchema[ProductResponse], summary="创建产品")
async def create_product(
        request: Request,
        product_in: ProductCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    创建新产品（已重构使用服务层）
    - 仅管理员可创建产品
    - 客户无权限创建产品，只能查看
    - 设置产品名称和减扣比例
    - 支持处理默认客户（导入数据）的特殊逻辑
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在ProductService中）
    product_service: ProductService = await get_product_service(db)
    
    # 准备产品数据
    product_data = product_in.model_dump()
    
    # 调用服务层创建产品（服务层会处理所有验证和默认客户逻辑）
    product = await product_service.create_product(product_data, current_user)

    # 记录创建操作
    # ---------- 异常处理 ----------
    try:
        await log_create(
            db=db,
            user=current_user,
            resource_type="PRODUCT",
            resource_id=product.id,
            resource_name=product.name,
            request=request,
            details={
                "name": product.name,
                "client_id": product.client_id,
                "ecpm_deduct_ratio": product.ecpm_deduct_ratio,
                "revenue_deduct_ratio": product.revenue_deduct_ratio,
                "is_active": product.is_active,
                "downstream_postback_url": product.downstream_postback_url,
                "downstream_postback_method": product.downstream_postback_method,
                "notification_address": product.notification_address
            }
        )
    except Exception as e:
        logger.error(f"记录产品创建审计日志失败: {str(e)}", exc_info=True)
    else:
        await commit_audit_log(db)

    # 重新加载并 selectinload(client)，避免响应序列化触发异步懒加载
    product = await product_service.get_product_by_id(
        product.id, current_user, include_client=True
    )
    return ResponseBaseSchema.success(data=build_product_response(product))


@router.put("/{product_id}", response_model=ResponseBaseSchema[ProductResponse], summary="更新产品")
async def update_product(
        request: Request,
        product_id: int = Path(..., ge=1, description="产品ID"),
        *,
        product_in: ProductUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    更新产品信息（已重构使用服务层）
    - 仅管理员可更新产品
    - 客户无权限更新产品，只能查看
    - 修改扣减比例后，不会更新现有的广告数据，新比例只影响未来导入的数据
    - 支持产品分配历史转移
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在ProductService中）
    product_service: ProductService = await get_product_service(db)
    
    # 获取更新数据（排除未设置的字段）
    update_data = product_in.model_dump(exclude_unset=True)

    product_before = await product_service.get_product_by_id(
        product_id, current_user, include_client=False
    )
    old_is_active = product_before.is_active
    old_ecpm_deduct_ratio = product_before.ecpm_deduct_ratio
    old_revenue_deduct_ratio = product_before.revenue_deduct_ratio

    product = await product_service.update_product(product_id, update_data, current_user)

    wrote_audit = False
    # ---------- 条件分支 ----------
    if "is_active" in update_data and update_data["is_active"] != old_is_active:
        # ---------- 条件分支 ----------
        if product.is_active:
            await log_activate(
                db=db,
                user=current_user,
                resource_type="PRODUCT",
                resource_id=product.id,
                resource_name=product.name,
                request=request,
            )
        else:
            await log_deactivate(
                db=db,
                user=current_user,
                resource_type="PRODUCT",
                resource_id=product.id,
                resource_name=product.name,
                request=request,
            )
        wrote_audit = True

    log_details = {
        **update_data,
        "note": "修改扣减比例后，不会更新现有广告数据，新比例只影响未来导入的数据"
    }
    # ---------- 条件分支 ----------
    if "ecpm_deduct_ratio" in update_data or "revenue_deduct_ratio" in update_data:
        deduct_ratio_changes = {}
        # ---------- 条件分支 ----------
        if "ecpm_deduct_ratio" in update_data:
            new_ecpm_ratio = update_data["ecpm_deduct_ratio"]
            deduct_ratio_changes["ecpm_deduct_ratio"] = {
                "old_value": old_ecpm_deduct_ratio,
                "new_value": new_ecpm_ratio,
                "change": f"{old_ecpm_deduct_ratio} → {new_ecpm_ratio}",
                "change_percentage": f"{(new_ecpm_ratio - old_ecpm_deduct_ratio) * 100:.2f}%",
            }
        # ---------- 条件分支 ----------
        if "revenue_deduct_ratio" in update_data:
            new_revenue_ratio = update_data["revenue_deduct_ratio"]
            deduct_ratio_changes["revenue_deduct_ratio"] = {
                "old_value": old_revenue_deduct_ratio,
                "new_value": new_revenue_ratio,
                "change": f"{old_revenue_deduct_ratio} → {new_revenue_ratio}",
                "change_percentage": f"{(new_revenue_ratio - old_revenue_deduct_ratio) * 100:.2f}%",
            }
        log_details["deduct_ratio_changes"] = deduct_ratio_changes
        log_details["is_deduct_ratio_adjusted"] = True

    # ---------- 条件分支 ----------
    if len(update_data) > 1 or "is_active" not in update_data:
        await log_update(
            db=db,
            user=current_user,
            resource_type="PRODUCT",
            resource_id=product_id,
            resource_name=product.name,
            request=request,
            details=log_details
        )
        wrote_audit = True

    # ---------- 条件分支 ----------
    if wrote_audit:
        await commit_audit_log(db)

    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data=build_product_response(product))


@router.delete("/{product_id}", response_model=ResponseBaseSchema[dict], summary="删除产品")
async def delete_product(
        request: Request,
        product_id: int = Path(..., ge=1, description="产品ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    删除产品（已重构使用服务层）
    - 仅管理员可删除产品
    - 客户无权限删除产品，只能查看
    - 删除规则：
      1. 如果产品关联了广告数据 → 将产品的 client_id 改为管理员的默认客户（不删除产品）
      2. 如果没有关联广告数据 → 直接删除产品
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在ProductService中）
    product_service: ProductService = await get_product_service(db)

    product = await product_service.get_product_by_id(
        product_id, current_user, include_client=False
    )

    count_result = await db.execute(
        select(func.count(AdData.id)).where(AdData.product_id == product_id)
    )
    ad_data_count = count_result.scalar() or 0

    # ---------- 条件分支 ----------
    if ad_data_count == 0:
        await log_delete(
            db=db,
            user=current_user,
            resource_type="PRODUCT",
            resource_id=product_id,
            resource_name=product.name,
            request=request,
            details={
                "client_id": product.client_id,
                "deleted": True
            }
        )
        await commit_audit_log(db)

    result = await product_service.delete_product(product_id, current_user)

    # ---------- 条件分支 ----------
    if result.get("transferred"):
        await log_update(
            db=db,
            user=current_user,
            resource_type="PRODUCT",
            resource_id=product_id,
            resource_name=product.name,
            request=request,
            details={
                "action": "transfer_to_admin_default_client",
                "new_client_id": result.get("new_client_id"),
                "ad_data_count": ad_data_count
            }
        )
        await commit_audit_log(db)
        return ResponseBaseSchema.success(data={
            "message": result["message"],
            "transferred": True,
            "new_client_id": result.get("new_client_id")
        })

    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data={"message": result["message"]})
