"""
重构示例：展示如何使用新架构模式

这个文件展示了如何将传统endpoint重构为使用新架构模式：
- 使用装饰器进行权限检查
- 使用服务层处理业务逻辑
- 使用统一响应格式
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
from app.core.response import (
    create_success_response,
    create_paginated_response
)
from app.models.models import User
# 注意：User 已在顶部导入，下面的局部导入是冗余的，但保留在示例中作为说明
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
    
    重构要点：
    1. 使用服务依赖注入
    2. 业务逻辑在服务层
    3. 使用统一响应格式
    """
    user = await user_service.get_user_by_id(user_id, current_user)
    return create_success_response(
        data=UserResponse.model_validate(user),
        message="查询成功"
    )


# ==================== 示例2：使用装饰器进行权限检查 ====================

@router.get("/admin/users", response_model=PaginatedResponseBaseSchema[list[UserResponse]])
@require_admin  # 使用装饰器，简化权限检查
@validate_pagination(max_page_size=100)  # 使用装饰器验证分页参数
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
    
    重构要点：
    1. 使用装饰器进行权限检查和参数验证
    2. 业务逻辑在服务层
    3. 使用统一响应格式
    """
    users, total = await user_service.get_users_paginated(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        current_user=current_user
    )

    return create_paginated_response(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size
    )


# ==================== 示例3：使用组合依赖项 ====================

@router.get("/admin/stats")
async def get_admin_stats_example(
        db_and_admin: DbAndAdminDep
):
    """
    获取管理员统计（重构示例）
    
    重构要点：
    1. 使用组合依赖项，一次性获取数据库和管理员用户
    2. 简化参数列表
    """
    db, admin = db_and_admin

    # 使用查询构建器直接查询（简单场景）
    # 注意：User 已在顶部导入
    builder = build_query(
        db=db,
        model=User,
        filters={"is_active": True}
    )
    active_count = await builder.count()

    return create_success_response(
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
    
    重构要点：
    1. 使用装饰器进行权限检查
    2. 业务逻辑（验证、创建）在服务层
    3. 使用统一响应格式
    """
    user = await user_service.create_user(user_data, current_user)
    return create_success_response(
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
    
    重构要点：
    1. 权限检查在服务层完成
    2. 业务逻辑在服务层
    3. 使用统一响应格式
    """
    user = await user_service.update_user(user_id, user_data, current_user)
    return create_success_response(
        data=UserResponse.model_validate(user),
        message="用户更新成功"
    )


# ==================== 示例6：删除操作 ====================

@router.delete("/users/{user_id}")
@require_admin
async def delete_user_example(
        user_id: int,
        user_service: UserServiceDep,
        current_user: CurrentUserDep
):
    """
    删除用户（重构示例）
    
    重构要点：
    1. 使用装饰器进行权限检查
    2. 业务逻辑（检查关联、删除）在服务层
    3. 使用统一响应格式
    """
    await user_service.delete_user(user_id, current_user)
    return create_success_response(message="用户删除成功")


# ==================== 示例7：使用查询构建器直接查询 ====================

@router.get("/users/search")
async def search_users_example(
        db: DatabaseDep,
        current_user: CurrentUserDep,
        keyword: str = Query(..., min_length=1)
):
    """
    搜索用户（重构示例）
    
    重构要点：
    1. 简单查询可以直接使用查询构建器
    2. 复杂查询建议在服务层
    """
    # 注意：User 已在顶部导入

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

    return create_paginated_response(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=1,
        page_size=20
    )


# ==================== 对比：重构前 vs 重构后 ====================

"""
重构前示例（不推荐）：

@router.get("/users/{user_id}")
async def get_user_old(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 权限检查
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise_api_exception(ErrorCode.FORBIDDEN, ...)
    
    # 查询逻辑
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise_api_exception(ErrorCode.USER_NOT_FOUND, ...)
    
    return ResponseBaseSchema.success(data=UserResponse.model_validate(user))

重构后示例（推荐）：

@router.get("/users/{user_id}")
async def get_user_new(
    user_id: int,
    user_service: UserServiceDep,
    current_user: CurrentUserDep
):
    user = await user_service.get_user_by_id(user_id, current_user)
    return create_success_response(
        data=UserResponse.model_validate(user),
        message="查询成功"
    )

优势：
1. 代码更简洁（从20+行减少到5行）
2. 权限检查在服务层，逻辑更清晰
3. 业务逻辑可复用
4. 易于测试
"""
