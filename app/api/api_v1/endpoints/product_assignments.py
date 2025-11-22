"""
产品分配历史管理API端点
提供产品分配历史的查询功能
"""
import logging
from fastapi import APIRouter, Depends, Path, Query, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import update

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.models import ProductAssignment, Product, Client, User, UserRole
from app.schemas.base import ResponseBaseSchema, ListResponseBaseSchema
from app.schemas.product_assignment import (
    ProductAssignmentResponse, 
    ProductAssignmentListResponse, 
    ProductAssignmentDateUpdate,
    BatchAssignmentsDateUpdateRequest,
    BatchAssignmentDateUpdate
)
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.product_assignment import validate_product_assignments, cleanup_invalid_assignments

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/products/{product_id}/assignments",
    response_model=ResponseBaseSchema[ProductAssignmentListResponse],
    summary="获取产品的分配历史"
)
async def get_product_assignments(
    request: Request,
    product_id: int = Path(..., ge=1, description="产品ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取指定产品的分配历史记录
    - 管理员可以查看任何产品的分配历史
    - 客户只能查看自己产品的分配历史
    """
    # 优化查询：一次性查询产品、客户、用户和分配历史，减少数据库往返
    if current_user.role == UserRole.ADMIN:
        # 管理员：直接查询分配历史，同时关联产品、客户和用户信息
        query = select(ProductAssignment, Client, Product, User).join(
            Client, ProductAssignment.client_id == Client.id
        ).join(
            Product, ProductAssignment.product_id == Product.id
        ).join(
            User, Client.user_id == User.id
        ).where(
            ProductAssignment.product_id == product_id
        ).order_by(ProductAssignment.start_date.desc())
    else:
        # 客户：需要验证权限，只查询属于当前客户的产品分配历史
        query = select(ProductAssignment, Client, Product, User).join(
            Client, ProductAssignment.client_id == Client.id
        ).join(
            Product, ProductAssignment.product_id == Product.id
        ).join(
            User, Client.user_id == User.id
        ).where(
            ProductAssignment.product_id == product_id,
            Client.user_id == current_user.id
        ).order_by(ProductAssignment.start_date.desc())
    
    result = await db.execute(query)
    assignments_data = result.all()
    
    # 检查是否有数据
    if not assignments_data:
        # 如果没有分配历史，检查产品是否存在（使用JOIN优化，避免N+1查询）
        product_query = select(Product).options(selectinload(Product.client)).where(Product.id == product_id)
        
        # 如果是客户角色，在查询时直接过滤权限
        if current_user.role != UserRole.ADMIN:
            product_query = product_query.join(Client, Product.client_id == Client.id).where(
                Client.user_id == current_user.id
            )
        
        product_result = await db.execute(product_query)
        product = product_result.scalars().first()
        
        if not product:
            # 如果是客户用户，可能是权限问题
            if current_user.role != UserRole.ADMIN:
                raise_api_exception(
                    ErrorCode.PRODUCT_NO_PERMISSION,
                    detail=f"您没有权限查看产品ID {product_id} 的分配历史"
                )
            else:
                raise_api_exception(
                    ErrorCode.PRODUCT_NOT_FOUND,
                    detail=f"产品ID {product_id} 不存在"
                )
    
    # 转换为响应格式
    assignments_list = []
    for row in assignments_data:
        # 解包查询结果（ProductAssignment, Client, Product, User）
        assignment, client, product, user = row
        assignment_dict = {
            "id": assignment.id,
            "product_id": assignment.product_id,
            "client_id": assignment.client_id,
            "start_date": assignment.start_date,
            "end_date": assignment.end_date,
            "created_at": assignment.created_at,
            "updated_at": assignment.updated_at,
            "client_name": client.company_name,
            "company_name": client.company_name,
            "contact_person": client.contact_person,  # 联系人
            "phone": client.phone,  # 电话
            "user_full_name": user.full_name if user else None  # 用户全名
        }
        assignments_list.append(ProductAssignmentResponse(**assignment_dict))
    
    return ResponseBaseSchema.success(
        data=ProductAssignmentListResponse(
            data=assignments_list,
            total=len(assignments_list)
        )
    )


@router.get(
    "/clients/{client_id}/assignments",
    response_model=ResponseBaseSchema[ProductAssignmentListResponse],
    summary="获取客户的分配历史（管理员）"
)
async def get_client_assignments(
    request: Request,
    client_id: int = Path(..., ge=1, description="客户ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    获取指定客户的所有产品分配历史记录（仅管理员）
    """
    # 检查客户是否存在 - 使用selectinload预加载用户信息
    client_query = select(Client).options(selectinload(Client.user)).where(Client.id == client_id)
    client_result = await db.execute(client_query)
    client = client_result.scalars().first()
    
    if not client:
        raise_api_exception(
            ErrorCode.CLIENT_NOT_FOUND,
            detail=f"客户ID {client_id} 不存在"
        )
    
    # 查询该客户的所有分配记录，按产品ID和开始日期排序，同时关联用户信息
    query = select(ProductAssignment, Product, User).join(
        Product, ProductAssignment.product_id == Product.id
    ).join(
        Client, ProductAssignment.client_id == Client.id
    ).join(
        User, Client.user_id == User.id
    ).where(
        ProductAssignment.client_id == client_id
    ).order_by(Product.id, ProductAssignment.start_date.desc())
    
    result = await db.execute(query)
    assignments_data = result.all()
    
    # 转换为响应格式
    assignments_list = []
    for assignment, product, user in assignments_data:
        assignment_dict = {
            "id": assignment.id,
            "product_id": assignment.product_id,
            "client_id": assignment.client_id,
            "start_date": assignment.start_date,
            "end_date": assignment.end_date,
            "created_at": assignment.created_at,
            "updated_at": assignment.updated_at,
            "client_name": client.company_name,
            "company_name": client.company_name,
            "contact_person": client.contact_person,  # 联系人
            "phone": client.phone,  # 电话
            "user_full_name": user.full_name if user else None  # 用户全名
        }
        assignments_list.append(ProductAssignmentResponse(**assignment_dict))
    
    return ResponseBaseSchema.success(
        data=ProductAssignmentListResponse(
            data=assignments_list,
            total=len(assignments_list)
        )
    )


@router.get(
    "/products/{product_id}/assignments/validate",
    response_model=ResponseBaseSchema[dict],
    summary="验证产品分配记录的逻辑完整性（管理员）"
)
async def validate_product_assignments_endpoint(
    request: Request,
    product_id: int = Path(..., ge=1, description="产品ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    验证产品分配记录的逻辑完整性
    
    检查以下问题：
    1. 重叠：两个客户不能同时拥有产品
    2. 空窗期：日期必须连续覆盖，不能有间隙
    3. 不连贯：日期必须按顺序排列
    4. 多个当前有效记录：应该只有一个当前有效的记录
    
    仅管理员可以访问此端点
    """
    # 检查产品是否存在
    product_query = select(Product).where(Product.id == product_id)
    product_result = await db.execute(product_query)
    product = product_result.scalars().first()
    
    if not product:
        raise_api_exception(
            ErrorCode.PRODUCT_NOT_FOUND,
            detail=f"产品ID {product_id} 不存在"
        )
    
    # 执行验证
    validation_result = await validate_product_assignments(db, product_id)
    
    # 构建响应
    is_valid = len(validation_result["errors"]) == 0
    response_data = {
        "product_id": product_id,
        "product_name": product.name,
        "is_valid": is_valid,
        "errors": validation_result["errors"],
        "warnings": validation_result["warnings"],
        "error_count": len(validation_result["errors"]),
        "warning_count": len(validation_result["warnings"])
    }
    
    if is_valid:
        return ResponseBaseSchema.success(
            data=response_data,
            message="产品分配记录验证通过，没有发现逻辑错误"
        )
    else:
        return ResponseBaseSchema.success(
            data=response_data,
            message=f"产品分配记录验证失败，发现 {len(validation_result['errors'])} 个错误"
        )


@router.post(
    "/products/{product_id}/assignments/cleanup",
    response_model=ResponseBaseSchema[dict],
    summary="清理产品分配记录中的无效数据（管理员）"
)
async def cleanup_product_assignments_endpoint(
    request: Request,
    product_id: int = Path(..., ge=1, description="产品ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    清理产品分配记录中的无效数据
    
    清理规则：
    1. 删除日期逻辑错误的记录（start_date > end_date）
    2. 删除重复的记录（同一产品、同一客户、同一天的多条记录，保留end_date为NULL的记录）
    3. 保留正确的记录（end_date为NULL的当前有效记录）
    
    仅管理员可以访问此端点
    """
    # 检查产品是否存在
    product_query = select(Product).where(Product.id == product_id)
    product_result = await db.execute(product_query)
    product = product_result.scalars().first()
    
    if not product:
        raise_api_exception(
            ErrorCode.PRODUCT_NOT_FOUND,
            detail=f"产品ID {product_id} 不存在"
        )
    
    # 执行清理
    cleanup_result = await cleanup_invalid_assignments(db, product_id)
    
    # 构建响应
    response_data = {
        "product_id": product_id,
        "product_name": product.name,
        "deleted_count": cleanup_result["deleted_count"],
        "deleted_records": cleanup_result["deleted_records"],
        "errors": cleanup_result["errors"],
        "has_errors": len(cleanup_result["errors"]) > 0
    }
    
    return ResponseBaseSchema.success(
        data=response_data,
        message=cleanup_result["message"]
    )


@router.post(
    "/assignments/cleanup-all",
    response_model=ResponseBaseSchema[dict],
    summary="清理所有产品的分配记录中的无效数据（管理员）"
)
async def cleanup_all_product_assignments_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    清理所有产品的分配记录中的无效数据
    
    清理规则：
    1. 删除日期逻辑错误的记录（start_date > end_date）
    2. 删除重复的记录（同一产品、同一客户、同一天的多条记录，保留end_date为NULL的记录）
    3. 保留正确的记录（end_date为NULL的当前有效记录）
    
    仅管理员可以访问此端点
    """
    # 执行清理（product_id为None表示清理所有产品）
    cleanup_result = await cleanup_invalid_assignments(db, product_id=None)
    
    # 构建响应
    response_data = {
        "deleted_count": cleanup_result["deleted_count"],
        "deleted_records": cleanup_result["deleted_records"],
        "errors": cleanup_result["errors"],
        "has_errors": len(cleanup_result["errors"]) > 0
    }
    
    return ResponseBaseSchema.success(
        data=response_data,
        message=cleanup_result["message"]
    )


@router.put(
    "/assignments/{assignment_id}/dates",
    response_model=ResponseBaseSchema[ProductAssignmentResponse],
    summary="更新产品分配历史的日期（管理员）"
)
async def update_assignment_dates(
    request: Request,
    assignment_id: int = Path(..., ge=1, description="分配记录ID"),
    date_update: ProductAssignmentDateUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    更新产品分配历史的日期
    
    功能：
    1. 更新指定分配记录的开始日期和/或结束日期
    2. 自动验证时间连贯性（无重叠、无空窗期）
    3. 如果验证失败，回滚更改并返回错误信息
    
    仅管理员可以访问此端点
    """
    from datetime import timedelta
    
    # 查询分配记录
    query = select(ProductAssignment).where(ProductAssignment.id == assignment_id)
    result = await db.execute(query)
    assignment = result.scalars().first()
    
    if not assignment:
        raise_api_exception(
            ErrorCode.NOT_FOUND,
            detail=f"分配记录ID {assignment_id} 不存在"
        )
    
    # 保存原始值用于回滚
    original_start_date = assignment.start_date
    original_end_date = assignment.end_date
    
    # 准备更新的值
    # 使用exclude_unset=True来区分"字段未提供"和"字段为None"
    # 如果字段在请求中未提供，不会包含在update_data中，使用原值
    # 如果字段在请求中明确提供（即使是None），使用新值
    update_data = date_update.model_dump(exclude_unset=True)
    new_start_date = update_data.get('start_date', assignment.start_date)
    new_end_date = update_data.get('end_date', assignment.end_date)
    
    # 基本验证：如果end_date不为None，必须满足 start_date <= end_date
    if new_end_date is not None and new_start_date > new_end_date:
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=f"日期逻辑错误：开始日期（{new_start_date}）不能大于结束日期（{new_end_date}）"
        )
    
    # 更新分配记录
    assignment.start_date = new_start_date
    assignment.end_date = new_end_date
    await db.flush()
    
    # 验证更新后的分配记录连贯性
    try:
        # 执行验证
        validation_result = await validate_product_assignments(db, assignment.product_id)
        
        if validation_result["errors"]:
            # 验证失败：回滚更改（rollback会自动撤销所有未提交的更改）
            await db.rollback()
            
            error_msg = "; ".join(validation_result["errors"])
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"日期更新后验证失败：{error_msg}。请确保日期不重叠且无空窗期。"
            )
        
        # 验证通过，在提交前先查询关联信息（避免commit后查询问题）
        # 使用JOIN查询关联对象（更可靠，避免selectinload的嵌套问题）
        query_with_relations = select(ProductAssignment, Client, Product, User).join(
            Client, ProductAssignment.client_id == Client.id
        ).join(
            Product, ProductAssignment.product_id == Product.id
        ).outerjoin(
            User, Client.user_id == User.id
        ).where(
            ProductAssignment.id == assignment_id
        )
        result_with_relations = await db.execute(query_with_relations)
        row = result_with_relations.first()
        
        if not row:
            await db.rollback()
            logger.error(f"更新分配记录 {assignment_id} 后无法查询到记录")
            raise_api_exception(
                ErrorCode.INTERNAL_ERROR,
                detail="更新后无法查询到记录"
            )
        
        # 解包查询结果
        assignment_with_relations, client, product, user = row
        
        # 构建响应数据
        assignment_dict = {
            "id": assignment_with_relations.id,
            "product_id": assignment_with_relations.product_id,
            "client_id": assignment_with_relations.client_id,
            "start_date": assignment_with_relations.start_date,
            "end_date": assignment_with_relations.end_date,
            "created_at": assignment_with_relations.created_at,
            "updated_at": assignment_with_relations.updated_at,
            "client_name": client.company_name if client else None,
            "company_name": client.company_name if client else None,
            "contact_person": client.contact_person if client else None,
            "phone": client.phone if client else None,
            "user_full_name": user.full_name if user else None
        }
        
        # 提交更改
        await db.commit()
        
        logger.info(
            f"管理员 {current_user.id} 更新了产品分配记录 {assignment_id} 的日期："
            f"开始日期 {original_start_date} -> {new_start_date}, "
            f"结束日期 {original_end_date or 'NULL'} -> {new_end_date or 'NULL'}"
        )
        
        return ResponseBaseSchema.success(
            data=ProductAssignmentResponse(**assignment_dict),
            message="日期更新成功，时间连贯性验证通过"
        )
            
    except Exception as e:
        # 回滚更改
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"回滚事务时出错: {str(rollback_error)}", exc_info=True)
        
        # 如果是我们自己的API异常（通过raise_api_exception抛出），直接重新抛出
        # raise_api_exception会抛出HTTPException，它有status_code属性
        if isinstance(e, HTTPException):
            raise e
        
        # 其他异常，记录并返回错误
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(
            f"更新分配记录 {assignment_id} 日期时出错: {str(e)}\n"
            f"错误堆栈:\n{error_traceback}",
            exc_info=True
        )
        raise_api_exception(
            ErrorCode.INTERNAL_ERROR,
            detail=f"更新日期时出错: {str(e)}"
        )


@router.put(
    "/assignments/batch-update-dates",
    response_model=ResponseBaseSchema[dict],
    summary="批量更新产品分配历史的日期（管理员）"
)
async def batch_update_assignment_dates(
    request: Request,
    batch_update: BatchAssignmentsDateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    批量更新产品分配历史的日期
    
    功能：
    1. 一次性更新多个分配记录的开始日期和/或结束日期
    2. 先应用所有更新（不提交），然后统一验证时间连贯性
    3. 如果验证失败，回滚所有更改并返回错误信息
    4. 如果验证通过，提交所有更改
    
    这样可以避免逐个更新时中间状态的验证错误
    
    仅管理员可以访问此端点
    """
    if not batch_update.updates or len(batch_update.updates) == 0:
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail="更新列表不能为空"
        )
    
    # 获取所有要更新的分配记录ID
    assignment_ids = [update.assignment_id for update in batch_update.updates]
    
    # 查询所有要更新的分配记录
    query = select(ProductAssignment).where(ProductAssignment.id.in_(assignment_ids))
    result = await db.execute(query)
    assignments = result.scalars().all()
    
    if len(assignments) != len(assignment_ids):
        found_ids = {a.id for a in assignments}
        missing_ids = set(assignment_ids) - found_ids
        raise_api_exception(
            ErrorCode.NOT_FOUND,
            detail=f"以下分配记录ID不存在: {', '.join(map(str, missing_ids))}"
        )
    
    # 创建ID到记录的映射
    assignment_map = {a.id: a for a in assignments}
    
    # 保存原始值用于日志
    original_values = {}
    for assignment in assignments:
        original_values[assignment.id] = {
            'start_date': assignment.start_date,
            'end_date': assignment.end_date
        }
    
    # 应用所有更新（不提交）
    for update_item in batch_update.updates:
        assignment = assignment_map[update_item.assignment_id]
        
        # 准备更新的值
        update_data = update_item.model_dump(exclude_unset=True, exclude={'assignment_id'})
        new_start_date = update_data.get('start_date', assignment.start_date)
        new_end_date = update_data.get('end_date', assignment.end_date)
        
        # 基本验证：如果end_date不为None，必须满足 start_date <= end_date
        if new_end_date is not None and new_start_date > new_end_date:
            await db.rollback()
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"记录ID {assignment.id}: 日期逻辑错误：开始日期（{new_start_date}）不能大于结束日期（{new_end_date}）"
            )
        
        # 更新分配记录
        assignment.start_date = new_start_date
        assignment.end_date = new_end_date
    
    # 刷新到数据库（但不提交）
    await db.flush()
    
    # 获取产品ID（所有记录应该属于同一个产品）
    product_id = assignments[0].product_id
    for assignment in assignments:
        if assignment.product_id != product_id:
            await db.rollback()
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="批量更新只能更新同一产品的分配记录"
            )
    
    # 验证所有更新后的分配记录连贯性
    try:
        # 执行验证（验证整个产品的所有记录）
        validation_result = await validate_product_assignments(db, product_id)
        
        if validation_result["errors"]:
            # 验证失败：回滚所有更改
            await db.rollback()
            
            error_msg = "; ".join(validation_result["errors"])
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"批量更新后验证失败：{error_msg}。请确保日期不重叠且无空窗期。"
            )
        
        # 验证通过，提交所有更改
        await db.commit()
        
        # 记录日志
        update_summary = []
        for update_item in batch_update.updates:
            assignment_id = update_item.assignment_id
            original = original_values[assignment_id]
            assignment = assignment_map[assignment_id]
            update_summary.append(
                f"记录ID {assignment_id}: "
                f"开始日期 {original['start_date']} -> {assignment.start_date}, "
                f"结束日期 {original['end_date'] or 'NULL'} -> {assignment.end_date or 'NULL'}"
            )
        
        logger.info(
            f"管理员 {current_user.id} 批量更新了产品 {product_id} 的 {len(batch_update.updates)} 条分配记录：\n" +
            "\n".join(update_summary)
        )
        
        return ResponseBaseSchema.success(
            data={
                "updated_count": len(batch_update.updates),
                "product_id": product_id,
                "message": f"成功批量更新 {len(batch_update.updates)} 条记录，时间连贯性验证通过"
            },
            message=f"批量更新成功，共更新 {len(batch_update.updates)} 条记录"
        )
            
    except Exception as e:
        # 回滚所有更改
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"回滚事务时出错: {str(rollback_error)}", exc_info=True)
        
        # 如果是我们自己的API异常，直接重新抛出
        if isinstance(e, HTTPException):
            raise e
        
        # 其他异常，记录并返回错误
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(
            f"批量更新分配记录日期时出错: {str(e)}\n"
            f"错误堆栈:\n{error_traceback}",
            exc_info=True
        )
        raise_api_exception(
            ErrorCode.INTERNAL_ERROR,
            detail=f"批量更新分配记录日期时出错: {str(e)}"
        )
