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

from app.core.audit_log import log_update, log_delete, log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.dependencies import get_product_assignment_service
from app.models.models import ProductAssignment, Product, Client, User, UserRole
from app.schemas.base import ResponseBaseSchema, ListResponseBaseSchema
from app.schemas.product_assignment import (
    ProductAssignmentResponse, 
    ProductAssignmentDateUpdate,
    BatchAssignmentsDateUpdateRequest,
    BatchAssignmentDateUpdate
)
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.product_assignment import validate_product_assignments, cleanup_invalid_assignments
from app.services.product_assignment_service import ProductAssignmentService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/products/{product_id}/assignments",
    response_model=ListResponseBaseSchema[list[ProductAssignmentResponse]],
    summary="获取产品的分配历史"
)
async def get_product_assignments(
    request: Request,
    product_id: int = Path(..., ge=1, description="产品ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取指定产品的分配历史记录（已重构使用服务层）
    - 管理员可以查看任何产品的分配历史
    - 客户只能查看自己产品的分配历史
    """
    # 使用服务层（业务逻辑在ProductAssignmentService中）
    assignment_service: ProductAssignmentService = await get_product_assignment_service(db)
    
    # 调用服务层获取产品分配历史（服务层会处理查询、权限检查）
    assignments_list = await assignment_service.get_product_assignments(product_id, current_user)
    
    # 转换为响应格式
    assignments = [ProductAssignmentResponse(**item) for item in assignments_list]
    
    return ListResponseBaseSchema.success(
        data=assignments,
        count=len(assignments)
    )


@router.get(
    "/clients/{client_id}/assignments",
    response_model=ListResponseBaseSchema[list[ProductAssignmentResponse]],
    summary="获取客户的分配历史（管理员）"
)
async def get_client_assignments(
    request: Request,
    client_id: int = Path(..., ge=1, description="客户ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    获取指定客户的所有产品分配历史记录（仅管理员，已重构使用服务层）
    """
    # 使用服务层（业务逻辑在ProductAssignmentService中）
    assignment_service: ProductAssignmentService = await get_product_assignment_service(db)
    
    # 调用服务层获取客户分配历史（服务层会处理查询和验证）
    assignments_list = await assignment_service.get_client_assignments(client_id, current_user)
    
    # 转换为响应格式
    assignments = [ProductAssignmentResponse(**item) for item in assignments_list]
    
    return ListResponseBaseSchema.success(
        data=assignments,
        count=len(assignments)
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
    验证产品分配记录的逻辑完整性（已重构使用服务层）
    
    检查以下问题：
    1. 重叠：两个客户不能同时拥有产品
    2. 空窗期：日期必须连续覆盖，不能有间隙
    3. 不连贯：日期必须按顺序排列
    4. 多个当前有效记录：应该只有一个当前有效的记录
    
    仅管理员可以访问此端点
    """
    # 使用服务层（业务逻辑在ProductAssignmentService中）
    assignment_service: ProductAssignmentService = await get_product_assignment_service(db)
    
    # 调用服务层验证产品分配记录（服务层会处理验证）
    response_data = await assignment_service.validate_product_assignments(product_id, current_user)
    
    is_valid = response_data["is_valid"]
    if is_valid:
        return ResponseBaseSchema.success(
            data=response_data,
            message="产品分配记录验证通过，没有发现逻辑错误"
        )
    else:
        return ResponseBaseSchema.success(
            data=response_data,
            message=f"产品分配记录验证失败，发现 {response_data['error_count']} 个错误"
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
    清理产品分配记录中的无效数据（已重构使用服务层）
    
    清理规则：
    1. 删除日期逻辑错误的记录（start_date > end_date）
    2. 删除重复的记录（同一产品、同一客户、同一天的多条记录，保留end_date为NULL的记录）
    3. 保留正确的记录（end_date为NULL的当前有效记录）
    
    仅管理员可以访问此端点
    """
    # 使用服务层（业务逻辑在ProductAssignmentService中）
    assignment_service: ProductAssignmentService = await get_product_assignment_service(db)
    
    # 调用服务层清理产品分配记录（服务层会处理清理）
    response_data = await assignment_service.cleanup_product_assignments(product_id, current_user)

    if response_data.get("deleted_count", 0) > 0:
        await log_delete(
            db=db,
            user=current_user,
            resource_type="PRODUCT_ASSIGNMENT",
            resource_id=product_id,
            resource_name=f"产品分配清理-{product_id}",
            request=request,
            details={
                "deleted_count": response_data["deleted_count"],
                "scope": "single_product",
            },
        )
        await commit_audit_log(db)

    return ResponseBaseSchema.success(
        data=response_data,
        message=response_data["message"]
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
    清理所有产品的分配记录中的无效数据（已重构使用服务层）
    
    清理规则：
    1. 删除日期逻辑错误的记录（start_date > end_date）
    2. 删除重复的记录（同一产品、同一客户、同一天的多条记录，保留end_date为NULL的记录）
    3. 保留正确的记录（end_date为NULL的当前有效记录）
    
    仅管理员可以访问此端点
    """
    # 使用服务层（业务逻辑在ProductAssignmentService中）
    assignment_service: ProductAssignmentService = await get_product_assignment_service(db)
    
    # 调用服务层清理所有产品分配记录（服务层会处理清理）
    response_data = await assignment_service.cleanup_all_product_assignments(current_user)

    if response_data.get("deleted_count", 0) > 0:
        await log_delete(
            db=db,
            user=current_user,
            resource_type="PRODUCT_ASSIGNMENT",
            resource_id=0,
            resource_name="全部产品分配清理",
            request=request,
            details={
                "deleted_count": response_data["deleted_count"],
                "scope": "all_products",
            },
        )
        await commit_audit_log(db)

    return ResponseBaseSchema.success(
        data=response_data,
        message=response_data["message"]
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
    更新产品分配历史的日期（已重构使用服务层）
    
    功能：
    1. 更新指定分配记录的开始日期和/或结束日期
    2. 自动验证时间连贯性（无重叠、无空窗期）
    3. 如果验证失败，回滚更改并返回错误信息
    
    仅管理员可以访问此端点
    """
    # 使用服务层（业务逻辑在ProductAssignmentService中）
    assignment_service: ProductAssignmentService = await get_product_assignment_service(db)
    
    # 准备更新数据
    update_data = date_update.model_dump(exclude_unset=True)
    
    # 调用服务层更新分配记录日期（服务层会处理验证、回滚等）
    assignment_dict = await assignment_service.update_assignment_dates(
        assignment_id, update_data, current_user
    )

    if update_data:
        await log_update(
            db=db,
            user=current_user,
            resource_type="PRODUCT_ASSIGNMENT",
            resource_id=assignment_id,
            resource_name=f"产品分配-{assignment_id}",
            request=request,
            details={"updated_fields": list(update_data.keys())},
        )
        await commit_audit_log(db)

    return ResponseBaseSchema.success(
        data=ProductAssignmentResponse(**assignment_dict),
        message="日期更新成功，时间连贯性验证通过"
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
    批量更新产品分配历史的日期（已重构使用服务层）
    
    功能：
    1. 一次性更新多个分配记录的开始日期和/或结束日期
    2. 先应用所有更新（不提交），然后统一验证时间连贯性
    3. 如果验证失败，回滚所有更改并返回错误信息
    4. 如果验证通过，提交所有更改
    
    这样可以避免逐个更新时中间状态的验证错误
    
    仅管理员可以访问此端点
    """
    # 使用服务层（业务逻辑在ProductAssignmentService中）
    assignment_service: ProductAssignmentService = await get_product_assignment_service(db)
    
    # 准备批量更新数据
    updates = []
    for update_item in batch_update.updates:
        update_data = update_item.model_dump(exclude_unset=True, exclude={'assignment_id'})
        update_data['assignment_id'] = update_item.assignment_id
        updates.append(update_data)
    
    # 调用服务层批量更新分配记录日期（服务层会处理验证、回滚等）
    result = await assignment_service.batch_update_assignment_dates(updates, current_user)

    await log_update(
        db=db,
        user=current_user,
        resource_type="PRODUCT_ASSIGNMENT",
        resource_id=result.get("product_id", 0),
        resource_name=f"产品分配批量更新",
        request=request,
        details={
            "updated_count": result.get("updated_count"),
            "product_id": result.get("product_id"),
        },
    )
    await commit_audit_log(db)

    return ResponseBaseSchema.success(
        data=result,
        message=f"批量更新成功，共更新 {result['updated_count']} 条记录"
    )
