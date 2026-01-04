"""
产品管理API端点模块

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
5. 所有操作都记录审计日志
"""
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
from app.core.audit_log import log_create, log_update, log_delete, log_activate, log_deactivate
from app.core.validation import sanitize_input
from app.core.constants import MAX_PAGE_SIZE
from app.core.product_assignment import (
    transfer_product_assignment,
    initialize_product_assignment,
    close_active_assignment
)
from app.models.models import AdData, Client, Product, User, UserRole
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema, ListResponseBaseSchema
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from datetime import date

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


# 用于返回的产品简要信息模型
class ProductNameOption(BaseModel):
    id: int
    name: str
    client_id: int

    class Config:
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
    try:
        # 1. 查找所有管理员用户和关联的客户 - 使用JOIN优化，一次性查询
        # 优化：使用JOIN一次性获取管理员用户及其关联的客户ID，减少查询次数
        admin_clients_query = select(Client.id).join(
            User, Client.user_id == User.id
        ).where(User.role == UserRole.ADMIN)
        admin_clients_result = await db.execute(admin_clients_query)
        admin_client_ids = [row[0] for row in admin_clients_result.all()]

        # 3. 构建查询：获取关联管理员的客户的产品和其他客户的产品
        products_query = select(Product).where(
            Product.name.isnot(None),
            Product.name != ''
        )

        # 如果指定了要排除的客户ID，排除该客户已有的所有产品（包括转移后的产品）
        if exclude_client_id:
            # 明确排除当前客户的所有产品（client_id == exclude_client_id）
            # 返回：关联管理员的客户的产品（排除当前客户的） + 其他客户的产品（排除当前客户的）
            if admin_client_ids:
                # 排除当前客户的产品，保留关联管理员的客户的产品和其他客户的产品
                products_query = products_query.where(Product.client_id != exclude_client_id)
            else:
                # 如果没有管理员客户，只返回其他客户的产品（排除当前客户）
                products_query = products_query.where(Product.client_id != exclude_client_id)
        else:
            # 如果没有指定排除客户ID，返回关联管理员的客户的产品和所有其他客户的产品
            if admin_client_ids:
                # 返回所有产品（包括管理员客户和其他客户）
                pass  # 不需要额外过滤
            else:
                # 如果没有管理员客户，返回所有产品
                pass

        # 4. 应用搜索过滤（优先使用全文搜索，回退到LIKE）
        if search and search.strip():
            cleaned_search = sanitize_input(search.strip(), max_length=100)
            if cleaned_search:
                from app.core.fulltext_search import search_with_fulltext
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
        products = products_result.scalars().unique().all()

        # 6. 转换为响应模型
        product_options = []
        admin_client_ids_set = set(admin_client_ids)  # 转换为set以提高查找效率
        for product in products:
            product_options.append(ProductNameOption(
                id=product.id,
                name=product.name,
                client_id=product.client_id
            ))

        # 7. 排序：优先显示关联管理员的客户的产品，然后按名称排序
        product_options.sort(key=lambda x: (
            0 if x.client_id in admin_client_ids_set else 1,  # 管理员客户的产品排前面（0 < 1）
            x.name  # 然后按名称排序
        ))

        logger.debug(f"Available products: total={len(product_options)}")

        return ListResponseBaseSchema.success(data=product_options, count=len(product_options))
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
        is_active: bool | None = Query(None, description="是否激活过滤")
):
    """
    获取产品列表，支持分页和过滤
    - 管理员可查看所有产品
    - 客户只能查看自己的产品
    - 支持按客户ID、产品名称和激活状态过滤
    - 根据设备类型自动优化分页大小
    """
    # ====== 设备类型优化：自动调整分页大小 ======
    from app.core.utils import optimize_page_size_for_device
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)
    # 构建查询
    query = select(Product)

    # 根据用户角色设置权限过滤
    if current_user.role != UserRole.ADMIN:
        # 客户只能查看自己的产品
        # 优化：直接在JOIN中过滤，避免额外的Client查询
        query = query.join(Client, Product.client_id == Client.id)
        query = query.where(Client.user_id == current_user.id)
    elif client_id:
        # 管理员按客户ID过滤
        query = query.where(Product.client_id == client_id)

    # 其他过滤条件
    if name:
        # 使用全文搜索（优先）或LIKE查询
        from app.core.fulltext_search import search_with_fulltext
        query = await search_with_fulltext(
            db=db,
            model_class=Product,
            search_fields=["name"],
            search_term=name,
            base_query=query,
            use_fulltext=True
        )
    if is_active is not None:
        query = query.where(Product.is_active == is_active)

    # 计算偏移量
    offset = (page - 1) * page_size

    # 执行查询获取总数和分页数据
    # 计算总数
    total_query = select(func.count(Product.id)).select_from(Product)
    if current_user.role != UserRole.ADMIN:
        # 客户只能查看自己的产品，使用与主查询相同的JOIN逻辑
        total_query = total_query.join(Client, Product.client_id == Client.id)
        total_query = total_query.where(Client.user_id == current_user.id)
    elif client_id:
        total_query = total_query.where(Product.client_id == client_id)
    
    # 产品名称搜索（优先使用全文搜索，回退到LIKE）
    if name:
        from app.core.fulltext_search import search_with_fulltext
        total_query = await search_with_fulltext(
            db=db,
            model_class=Product,
            search_fields=["name"],
            search_term=name,
            base_query=total_query,
            use_fulltext=True
        )
    
    if is_active is not None:
        total_query = total_query.where(Product.is_active == is_active)

    total_result = await db.execute(total_query)
    total = total_result.scalar()

    # 获取分页数据
    result = await db.execute(query.order_by(Product.id).offset(offset).limit(page_size))
    products = result.scalars().unique().all()

    # 转换为响应模型
    product_responses = [ProductResponse.model_validate(product) for product in products]

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
    获取指定产品的详细信息
    - 管理员可查看所有产品
    - 客户只能查看自己的产品
    - 返回产品完整信息，包括减扣比例
    - 使用JOIN优化查询，避免N+1问题
    """
    # 构建查询 - 使用JOIN优化，避免N+1查询
    from sqlalchemy.orm import selectinload
    
    query = select(Product).options(selectinload(Product.client)).where(Product.id == product_id)
    
    # 如果是客户用户，在查询时直接过滤，避免额外查询
    if current_user.role != UserRole.ADMIN:
        query = query.join(Client, Product.client_id == Client.id).where(Client.user_id == current_user.id)
    
    result = await db.execute(query)
    product = result.scalars().first()

    if not product:
        # 如果是客户用户，可能是权限问题
        if current_user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.PRODUCT_NO_PERMISSION,
                detail=f"您没有权限访问产品ID {product_id}，该产品不属于您的客户账户"
            )
        else:
            raise_api_exception(
                ErrorCode.PRODUCT_NOT_FOUND,
                detail=f"产品ID {product_id} 不存在"
            )

    return ResponseBaseSchema.success(data=ProductResponse.model_validate(product))


@router.post("/", response_model=ResponseBaseSchema[ProductResponse], summary="创建产品")
async def create_product(
        request: Request,
        product_in: ProductCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    创建新产品
    - 仅管理员可创建产品
    - 客户无权限创建产品，只能查看
    - 设置产品名称和减扣比例
    """
    # 权限检查：仅管理员可创建产品
    if current_user.role == UserRole.ADMIN:
        # 管理员需要指定客户ID
        if not product_in.client_id:
            raise_api_exception(
                ErrorCode.PRODUCT_CLIENT_REQUIRED,
                detail="管理员创建产品时必须指定客户ID（client_id）"
            )
        client_id = product_in.client_id

        # 验证客户是否存在
        client_result = await db.execute(select(Client).where(Client.id == client_id))
        client = client_result.scalars().first()
        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"指定的客户ID {client_id} 不存在，请确认客户是否存在"
            )
    else:
        # 客户无权限创建产品（此代码不会执行，因为已使用require_admin）
        raise_api_exception(
            ErrorCode.PRODUCT_NO_PERMISSION,
            detail="客户用户没有权限创建产品，请联系管理员"
        )

    # 验证减扣比例是否在有效范围内
    if (product_in.ecpm_deduct_ratio < 0 or product_in.ecpm_deduct_ratio > 1) or \
            (product_in.revenue_deduct_ratio < 0 or product_in.revenue_deduct_ratio > 1):
        raise_api_exception(
            ErrorCode.PRODUCT_DEDUCT_RATIO_INVALID,
            detail=f"减扣比例必须在0到1之间。当前值：eCPM减扣比例={product_in.ecpm_deduct_ratio}, 收益减扣比例={product_in.revenue_deduct_ratio}"
        )

    # 检查当前客户是否已存在同名产品
    result = await db.execute(
        select(Product).where(
            Product.client_id == client_id,
            Product.name == product_in.name
        )
    )
    existing_product_for_client = result.scalars().first()
    if existing_product_for_client:
        raise_api_exception(
            ErrorCode.PRODUCT_ALREADY_EXISTS,
            detail=f"客户ID {client_id} 已存在同名产品：{product_in.name}。请使用不同的产品名称或更新现有产品"
        )

    # ====== 检查是否存在相同名称的产品属于默认客户（导入数据） ======
    # 查找相同名称的产品，并关联客户信息
    product_with_client_query = select(Product, Client).join(
        Client, Product.client_id == Client.id
    ).where(
        Product.name == product_in.name
    )
    product_with_client_result = await db.execute(product_with_client_query)
    products_with_clients = product_with_client_result.unique().all()

    # 查找属于默认客户（导入数据）的产品
    # 不管是不是管理员的用户，只要是"默认客户（导入数据）"就检查
    admin_default_product = None
    for product_obj, client_obj in products_with_clients:
        # 检查是否是默认客户（导入数据）（公司名称为"默认客户（导入数据）"）
        if client_obj.company_name == "默认客户（导入数据）":
            admin_default_product = product_obj
            break

    # 如果找到属于默认客户（导入数据）的产品，更新client_id而不是创建新产品
    if admin_default_product:
        logger.info(
            f"产品名称 '{product_in.name}' 属于默认客户（导入数据）（产品ID: {admin_default_product.id}，"
            f"原客户ID: {admin_default_product.client_id}），将更新为客户ID: {client_id}"
        )

        # 更新产品的client_id和扣减比例
        admin_default_product.client_id = client_id
        admin_default_product.ecpm_deduct_ratio = product_in.ecpm_deduct_ratio
        admin_default_product.revenue_deduct_ratio = product_in.revenue_deduct_ratio
        admin_default_product.is_active = product_in.is_active if product_in.is_active is not None else True
        # 更新下游 Postback 配置
        if product_in.downstream_postback_url is not None:
            admin_default_product.downstream_postback_url = product_in.downstream_postback_url
        if product_in.downstream_postback_method is not None:
            admin_default_product.downstream_postback_method = product_in.downstream_postback_method
        # 更新通知地址
        if product_in.notification_address is not None:
            admin_default_product.notification_address = product_in.notification_address

        try:
            await db.commit()
            await db.refresh(admin_default_product)
            logger.info(
                f"产品 '{product_in.name}' 已从默认客户（导入数据）转移到客户ID {client_id}，"
                f"并更新了扣减比例"
            )
            return ResponseBaseSchema.success(data=ProductResponse.model_validate(admin_default_product))
        except Exception as e:
            await db.rollback()
            logger.error(f"更新产品失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新产品失败: {str(e)}。请检查数据格式或联系管理员"
            )

    # 如果没有找到属于管理员默认客户的产品，创建新产品
    product = Product(
        client_id=client_id,
        name=product_in.name,
        ecpm_deduct_ratio=product_in.ecpm_deduct_ratio,
        revenue_deduct_ratio=product_in.revenue_deduct_ratio,
        is_active=product_in.is_active if product_in.is_active is not None else True,
        downstream_postback_url=product_in.downstream_postback_url,
        downstream_postback_method=product_in.downstream_postback_method or 'GET',
        notification_address=product_in.notification_address
    )

    # 保存到数据库
    try:
        db.add(product)
        await db.flush()  # 先flush以获取product.id
        
        # 初始化产品分配记录
        try:
            # 使用当前日期作为开始日期（新创建的产品）
            # 注意：product.created_at 在 flush() 后可能还未填充，所以直接使用 date.today()
            product_start_date = date.today()
            await initialize_product_assignment(
                db=db,
                product_id=product.id,
                client_id=product.client_id,
                start_date=product_start_date
            )
            logger.info(f"产品 {product.id} 的分配记录已初始化：客户 {product.client_id}，开始日期: {product_start_date}")
        except Exception as e:
            logger.warning(f"初始化产品分配记录失败: {str(e)}，但产品创建继续")
            # 分配记录初始化失败不影响产品创建，继续执行
        
        await db.commit()
        await db.refresh(product)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建产品失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建产品失败：{str(e)}。请检查数据格式或联系管理员"
        )

    logger.info(f"Product {product.name} created by {current_user.username}")

    # 记录创建操作（失败不影响产品创建）
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
        # 提交审计日志
        await db.commit()
    except Exception as e:
        # 审计日志记录失败不应该影响产品创建成功
        logger.error(f"记录产品创建审计日志失败: {str(e)}", exc_info=True)
        # 如果提交失败，回滚审计日志操作，但产品已经创建成功
        try:
            await db.rollback()
        except Exception:
            pass  # 忽略回滚错误

    # 构建响应数据，添加错误处理
    try:
        product_data = ProductResponse.model_validate(product)
        return ResponseBaseSchema.success(data=product_data)
    except Exception as e:
        logger.error(f"构建产品响应数据失败: {str(e)}", exc_info=True)
        # 即使响应构建失败，产品已经创建成功，返回基本信息
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"产品创建成功，但构建响应数据失败：{str(e)}。请刷新页面查看新创建的产品"
        )


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
    更新产品信息
    - 仅管理员可更新产品
    - 客户无权限更新产品，只能查看
    - 修改扣减比例后，不会更新现有的广告数据，新比例只影响未来导入的数据
    """
    # 获取产品
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()

    if not product:
        raise_api_exception(
            ErrorCode.PRODUCT_NOT_FOUND,
            detail=f"产品ID {product_id} 不存在"
        )

    # 权限检查：仅管理员可更新产品
    # 管理员可以更改产品所属客户（用于将其他客户的产品转移到当前客户）
    # 允许更新 client_id

    # 如果更改产品名称，检查是否已存在
    if product_in.name and product_in.name != product.name:
        result = await db.execute(
            select(Product).where(
                Product.client_id == product.client_id,
                Product.name == product_in.name
            )
        )
        existing_product = result.scalars().first()
        if existing_product:
            raise_api_exception(
                ErrorCode.PRODUCT_ALREADY_EXISTS,
                detail=f"客户ID {product.client_id} 已存在同名产品：{product_in.name}。请使用不同的产品名称"
            )

    # 记录旧的扣减比例，用于记录变更历史
    old_ecpm_deduct_ratio = product.ecpm_deduct_ratio
    old_revenue_deduct_ratio = product.revenue_deduct_ratio

    # 检查 is_active 是否改变（用于记录激活/禁用日志）
    old_is_active = product.is_active

    # 更新产品信息
    update_data = product_in.model_dump(exclude_unset=True)

    # 仅管理员可更新产品，无需额外权限检查

    # 验证减扣比例是否在有效范围内（仅管理员）
    if product_in.ecpm_deduct_ratio is not None and (
            product_in.ecpm_deduct_ratio < 0 or product_in.ecpm_deduct_ratio > 1):
        raise_api_exception(
            ErrorCode.PRODUCT_DEDUCT_RATIO_INVALID,
            detail=f"eCPM减扣比例必须在0到1之间。当前值：{product_in.ecpm_deduct_ratio}"
        )

    if product_in.revenue_deduct_ratio is not None and (
            product_in.revenue_deduct_ratio < 0 or product_in.revenue_deduct_ratio > 1):
        raise_api_exception(
            ErrorCode.PRODUCT_DEDUCT_RATIO_INVALID,
            detail=f"收益减扣比例必须在0到1之间。当前值：{product_in.revenue_deduct_ratio}"
        )

    # 如果是管理员且更改了 client_id，需要检查新客户是否已有同名产品，并记录分配历史
    old_client_id = product.client_id
    if current_user.role == UserRole.ADMIN and "client_id" in update_data and update_data[
        "client_id"] != product.client_id:
        new_client_id = update_data["client_id"]
        # 检查新客户是否已有同名产品
        existing_product_query = select(Product).where(
            Product.client_id == new_client_id,
            Product.name == product.name
        )
        existing_product_result = await db.execute(existing_product_query)
        existing_product = existing_product_result.scalars().first()
        if existing_product:
            raise_api_exception(
                ErrorCode.PRODUCT_ALREADY_EXISTS,
                detail=f"目标客户ID {new_client_id} 已存在同名产品：{product.name}。无法转移产品"
            )
        
        # 记录产品分配历史（转移产品）
        # 获取转移日期和旧客户结束日期
        transfer_date = update_data.get("transfer_date")
        old_client_end_date = update_data.get("old_client_end_date")
        
        # 验证日期
        if transfer_date and transfer_date > date.today():
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"新客户开始日期不能是未来日期：{transfer_date}"
            )
        
        if old_client_end_date and old_client_end_date > date.today():
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"旧客户结束日期不能是未来日期：{old_client_end_date}"
            )
        
        # 如果同时提供了两个日期，验证它们的关系
        if transfer_date and old_client_end_date:
            if old_client_end_date >= transfer_date:
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"旧客户结束日期（{old_client_end_date}）必须小于新客户开始日期（{transfer_date}）"
                )
            # 验证日期连续性：新客户开始日期应该是旧客户结束日期 + 1天（确保无空窗期）
            from datetime import timedelta
            expected_start_date = old_client_end_date + timedelta(days=1)
            if transfer_date != expected_start_date:
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"日期连续性错误：新客户开始日期（{transfer_date}）必须是旧客户结束日期（{old_client_end_date}）+ 1天，"
                    f"期望值：{expected_start_date}，以确保广告数据无空窗期"
                )
        
        # 从update_data中移除这些字段，因为它们不是Product模型的字段
        update_data.pop("transfer_date", None)
        update_data.pop("old_client_end_date", None)
        
        try:
            await transfer_product_assignment(
                db=db,
                product_id=product.id,
                old_client_id=old_client_id,
                new_client_id=new_client_id,
                transfer_date=transfer_date,
                old_client_end_date=old_client_end_date
            )
            logger.info(
                f"产品 {product.id} 的分配历史已更新："
                f"从客户 {old_client_id} 转移到客户 {new_client_id}，"
                f"新客户开始日期: {transfer_date or '自动计算'}，"
                f"旧客户结束日期: {old_client_end_date or '自动计算'}"
            )
        except ValueError as e:
            # 验证失败（如重叠、空窗期等），需要回滚并返回错误
            await db.rollback()
            logger.error(f"产品分配历史验证失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=str(e)
            )
        except Exception as e:
            # 其他异常（如数据库错误），记录日志但不影响产品转移
            logger.error(f"记录产品分配历史失败: {str(e)}", exc_info=True)
            # 分配历史记录失败不影响产品转移，继续执行

    for key, value in update_data.items():
        setattr(product, key, value)

    # 注意：修改扣减比例后，不再自动更新现有的广告数据
    # 新的扣减比例只影响未来导入的数据
    # 现有的广告数据保持原样，不会重新计算

    # 保存到数据库
    try:
        await db.commit()
        await db.refresh(product)
    except Exception as e:
        await db.rollback()
        logger.error(f"更新产品失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新产品失败：{str(e)}。请检查数据格式或联系管理员"
        )

    logger.info(f"Product {product.name} updated by {current_user.username}")

    # 检查 is_active 是否改变
    is_active_changed = "is_active" in update_data and update_data.get("is_active") != old_is_active

    # 如果 is_active 改变，记录激活/禁用日志
    if is_active_changed:
        if product.is_active:
            await log_activate(
                db=db,
                user=current_user,
                resource_type="PRODUCT",
                resource_id=product_id,
                resource_name=product.name,
                request=request
            )
        else:
            await log_deactivate(
                db=db,
                user=current_user,
                resource_type="PRODUCT",
                resource_id=product_id,
                resource_name=product.name,
                request=request
            )

    # 记录更新操作（详细记录扣减比例变更）
    update_data = product_in.model_dump(exclude_unset=True)

    # 构建详细的变更记录
    log_details = {
        **update_data,
        "note": "修改扣减比例后，不会更新现有广告数据，新比例只影响未来导入的数据"
    }

    # 如果修改了扣减比例，记录变更历史
    if "ecpm_deduct_ratio" in update_data or "revenue_deduct_ratio" in update_data:
        deduct_ratio_changes = {}

        if "ecpm_deduct_ratio" in update_data:
            new_ecpm_ratio = update_data["ecpm_deduct_ratio"]
            deduct_ratio_changes["ecpm_deduct_ratio"] = {
                "old_value": old_ecpm_deduct_ratio,
                "new_value": new_ecpm_ratio,
                "change": f"{old_ecpm_deduct_ratio} → {new_ecpm_ratio}",
                "change_percentage": f"{(new_ecpm_ratio - old_ecpm_deduct_ratio) * 100:.2f}%"
            }

        if "revenue_deduct_ratio" in update_data:
            new_revenue_ratio = update_data["revenue_deduct_ratio"]
            deduct_ratio_changes["revenue_deduct_ratio"] = {
                "old_value": old_revenue_deduct_ratio,
                "new_value": new_revenue_ratio,
                "change": f"{old_revenue_deduct_ratio} → {new_revenue_ratio}",
                "change_percentage": f"{(new_revenue_ratio - old_revenue_deduct_ratio) * 100:.2f}%"
            }

        log_details["deduct_ratio_changes"] = deduct_ratio_changes
        log_details["is_deduct_ratio_adjusted"] = True

    # 如果只更新了 is_active，不记录 UPDATE 日志（避免重复）
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

    return ResponseBaseSchema.success(data=ProductResponse.model_validate(product))


@router.delete("/{product_id}", response_model=ResponseBaseSchema[dict], summary="删除产品")
async def delete_product(
        request: Request,
        product_id: int = Path(..., ge=1, description="产品ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    删除产品（新的删除规则）
    - 仅管理员可删除产品
    - 客户无权限删除产品，只能查看
    - 删除规则：
      1. 如果产品关联了广告数据 → 将产品的 client_id 改为管理员的默认客户（不删除产品）
      2. 如果没有关联广告数据 → 直接删除产品
    """
    # 获取产品
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()

    if not product:
        raise_api_exception(
            ErrorCode.PRODUCT_NOT_FOUND,
            detail=f"产品ID {product_id} 不存在"
        )

    # 权限检查：仅管理员可删除产品

    # ====== 新的删除规则 ======
    # 1. 如果产品关联了广告数据 → 将产品的 client_id 改为默认客户（导入数据）
    # 2. 如果没有关联广告数据 → 直接删除产品

    # 检查是否有广告数据关联
    count_result = await db.execute(
        select(func.count(AdData.id)).where(AdData.product_id == product_id)
    )
    ad_data_count = count_result.scalar() or 0

    if ad_data_count > 0:
        # 有关联广告数据：将产品转移到默认客户（导入数据）
        logger.info(
            f"产品 {product.name} (ID: {product_id}) 关联了 {ad_data_count} 条广告数据，"
            f"将转移到默认客户（导入数据）"
        )

        # 查找或创建默认客户
        # 当前用户必须是管理员（已通过require_admin验证）
        admin_user = current_user

        # 查找或创建管理员的默认客户（导入数据）：使用统一的辅助函数
        from app.core.utils import find_or_create_default_client
        admin_default_client = await find_or_create_default_client(db, admin_user.id)

        # 保存旧客户ID（用于更新分配历史）
        old_client_id = product.client_id
        
        # 检查管理员的默认客户是否已有同名产品
        existing_product_query = select(Product).where(
            Product.client_id == admin_default_client.id,
            Product.name == product.name,
            Product.id != product_id  # 排除当前产品
        )
        existing_product_result = await db.execute(existing_product_query)
        existing_product = existing_product_result.scalars().first()

        if existing_product:
            # 如果默认客户（导入数据）已有同名产品，更新现有产品的扣减比例为0（如果需要）
            logger.warning(
                f"默认客户（导入数据）已存在同名产品 '{product.name}' (ID: {existing_product.id})，"
                f"将产品转移到该客户（ID: {admin_default_client.id}）"
            )
            # 仍然转移，覆盖同名产品的情况
            product.client_id = admin_default_client.id
            product.ecpm_deduct_ratio = 0.0
            product.revenue_deduct_ratio = 0.0
        else:
            # 将产品的 client_id 改为默认客户（导入数据）
            product.client_id = admin_default_client.id
            product.ecpm_deduct_ratio = 0.0
            product.revenue_deduct_ratio = 0.0

            logger.info(
                f"产品 '{product.name}' (ID: {product_id}) 已从客户ID {old_client_id} "
                f"转移到默认客户（导入数据）（ID: {admin_default_client.id}）"
            )

        # 更新产品分配历史（确保广告数据查询时能正确归属）
        try:
            await transfer_product_assignment(
                db=db,
                product_id=product.id,
                old_client_id=old_client_id,
                new_client_id=admin_default_client.id,
                transfer_date=date.today()  # 使用当前日期作为转移日期
            )
            logger.info(
                f"产品 {product.id} 的分配历史已更新："
                f"从客户 {old_client_id} 转移到默认客户 {admin_default_client.id}"
            )
        except Exception as e:
            logger.error(f"更新产品分配历史失败: {str(e)}", exc_info=True)
            # 分配历史更新失败不影响产品转移，继续执行

        # 保存更改
        try:
            await db.commit()
            await db.refresh(product)
            logger.debug(f"产品 '{product.name}' 已成功转移到默认客户（导入数据）")

            # 记录更新操作（产品转移）
            await log_update(
                db=db,
                user=current_user,
                resource_type="PRODUCT",
                resource_id=product_id,
                resource_name=product.name,
                request=request,
                details={
                    "action": "transfer_to_admin_default_client",
                    "old_client_id": product.client_id,
                    "new_client_id": admin_default_client.id,
                    "ad_data_count": ad_data_count
                }
            )

            return ResponseBaseSchema.success(data={
                "message": f"产品已转移到默认客户（导入数据）（该产品关联了 {ad_data_count} 条广告数据）",
                "transferred": True,
                "new_client_id": admin_default_client.id
            })
        except Exception as e:
            await db.rollback()
            logger.error(f"转移产品失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"转移产品失败：{str(e)}。请检查数据或联系管理员"
            )
    else:
        # 没有关联广告数据：直接删除产品
        logger.debug(f"产品 {product.name} (ID: {product_id}) 没有关联广告数据，将直接删除")

        try:
            # SQLAlchemy 2.0 正确的删除方式
            await db.delete(product)
            await db.commit()
            logger.info(f"Product {product.name} deleted by {current_user.username}")

            # 记录删除操作
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

            return ResponseBaseSchema.success(data={"message": "产品已成功删除"})
        except Exception as e:
            await db.rollback()
            logger.error(f"删除产品失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"删除产品失败：{str(e)}。请稍后重试或联系管理员"
            )
