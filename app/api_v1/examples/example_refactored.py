"""
重构示例：展示如何使用新架构模式

这个文件展示了如何将传统endpoint重构为使用新架构模式：
- 使用装饰器进行权限检查
- 使用服务层处理业务逻辑
- 使用统一响应格式（ResponseBaseSchema，code=200）
- 使用查询构建器优化查询
"""
from typing import Optional

from fastapi import APIRouter, Query

from app.core.decorators import require_admin, validate_pagination
from app.core.dependencies import (
    UserServiceDep,
    CurrentUserDep,
    DatabaseDep,
    DbAndAdminDep
)
from app.core.query_builder import build_query
from app.models.models import User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.user import UserResponse, UserCreate, UserUpdate

router = APIRouter()


# ==================== 示例1：使用装饰器和服务层 ====================

@router.get("/users/{user_id}", response_model=ResponseBaseSchema[UserResponse])
async def get_user_example(
        user_id: int,
        user_service: UserServiceDep,
        current_user: CurrentUserDep
):
    """
    获取用户详情（重构示例）
    """
    user = await user_service.get_user_by_id(user_id, current_user)
    return ResponseBaseSchema.success(
        data=UserResponse.model_validate(user),
        message="查询成功"
    )


# ==================== 示例2：使用装饰器进行权限检查 ====================

@router.get("/admin/users", response_model=PaginatedResponseBaseSchema[list[UserResponse]])
@require_admin
@validate_pagination(max_page_size=100)
async def get_users_example(
        user_service: UserServiceDep,
        current_user: CurrentUserDep,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        search: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None)
):
    """
    获取用户列表（重构示例）
    """
    users, total = await user_service.get_users_paginated(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        current_user=current_user
    )

    return PaginatedResponseBaseSchema.success(
        data=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        message="查询成功"
    )


# ==================== 示例3：使用组合依赖项 ====================

@router.get("/admin/stats", response_model=ResponseBaseSchema[dict])
async def get_admin_stats_example(
        db_and_admin: DbAndAdminDep
):
    """
    获取管理员统计（重构示例）
    """
    db, admin = db_and_admin
    builder = build_query(
        db=db,
        model=User,
        filters={"is_active": True}
    )
    active_count = await builder.count()

    return ResponseBaseSchema.success(
        data={"active_users": active_count},
        message="统计查询成功"
    )


# ==================== 示例4：创建操作 ====================

@router.post("/users", response_model=ResponseBaseSchema[UserResponse])
@require_admin
async def create_user_example(
        user_data: UserCreate,
        user_service: UserServiceDep,
        current_user: CurrentUserDep
):
    """
    创建用户（重构示例）
    """
    user = await user_service.create_user(user_data, current_user)
    return ResponseBaseSchema.success(
        data=UserResponse.model_validate(user),
        message="用户创建成功"
    )


# ==================== 示例5：更新操作 ====================

@router.put("/users/{user_id}", response_model=ResponseBaseSchema[UserResponse])
async def update_user_example(
        user_id: int,
        user_data: UserUpdate,
        user_service: UserServiceDep,
        current_user: CurrentUserDep
):
    """
    更新用户（重构示例）
    """
    user = await user_service.update_user(user_id, user_data, current_user)
    return ResponseBaseSchema.success(
        data=UserResponse.model_validate(user),
        message="用户更新成功"
    )


# ==================== 示例6：删除操作 ====================

@router.delete("/users/{user_id}", response_model=ResponseBaseSchema[None])
@require_admin
async def delete_user_example(
        user_id: int,
        user_service: UserServiceDep,
        current_user: CurrentUserDep
):
    """
    删除用户（重构示例）
    """
    await user_service.delete_user(user_id, current_user)
    return ResponseBaseSchema.success(message="用户删除成功")


# ==================== 示例7：使用查询构建器直接查询 ====================

@router.get("/users/search", response_model=PaginatedResponseBaseSchema[list[UserResponse]])
async def search_users_example(
        db: DatabaseDep,
        current_user: CurrentUserDep,
        keyword: str = Query(..., min_length=1)
):
    """
    搜索用户（重构示例）
    """
    builder = build_query(
        db=db,
        model=User,
        search_fields=["username", "email", "full_name"],
        search_keyword=keyword,
        order_by_field="created_at",
        page=1,
        page_size=20
    )

    users, total = await builder.paginated(1, 20)

    return PaginatedResponseBaseSchema.success(
        data=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=1,
        page_size=20,
        message="查询成功"
    )


# ==================== 对比：重构前 vs 重构后 ====================

"""
重构后统一使用 ResponseBaseSchema / PaginatedResponseBaseSchema（code=200 表示成功）。
勿使用已弃用的 app.core.response.ResponseBase（code=0）。
"""
