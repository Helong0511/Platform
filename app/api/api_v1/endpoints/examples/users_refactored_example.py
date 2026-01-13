"""
用户管理API端点 - 重构示例
展示如何使用服务层重构endpoint

注意：这是示例文件，展示重构后的代码结构
实际重构时，应该直接修改 users.py
"""
from fastapi import APIRouter, Depends, Query, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.dependencies import get_user_service, CurrentUserDep, DatabaseDep
from app.services.user_service import UserService
from app.models.models import User
from app.schemas.user import UserResponse, UserCreate, UserUpdate, PasswordChange
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.core.infrastructure.cache import cached, CacheInvalidator
from app.core.utils import optimize_page_size_for_device
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 示例1：获取用户列表（使用服务层） ====================
@router.get("/", response_model=PaginatedResponseBaseSchema[list[UserResponse]], summary="获取用户列表")
async def get_users(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    username: Optional[str] = Query(None, description="用户名过滤"),
    role: Optional[str] = Query(None, description="角色过滤"),
    status: Optional[str] = Query(None, description="状态过滤: active/inactive"),
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin)
):
    """
    获取用户列表（重构后版本）
    
    重构说明：
    - 业务逻辑已移到 UserService.get_users()
    - endpoint只负责HTTP参数处理和响应格式化
    - 代码更简洁，易于维护
    """
    # 设备类型优化（保留在endpoint中，因为需要Request对象）
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)
    
    # 状态转换
    is_active = None
    if status:
        if status.lower() == 'active':
            is_active = True
        elif status.lower() == 'inactive':
            is_active = False
    
    # 调用服务层（业务逻辑在服务层）
    users, total = await user_service.get_users(
        current_user=current_user,
        page=page,
        page_size=page_size,
        username=username,
        role=role,
        is_active=is_active
    )
    
    # 转换为响应模型（处理客户信息）
    user_responses = []
    for user in users:
        # 获取客户信息（如果用户是客户角色）
        client_data = None
        if user.role.value == 'client' and user.clients:
            client = user.clients[0]  # 客户用户通常只有一个客户
            client_data = {
                'id': client.id,
                'company_name': client.company_name,
                'contact_person': client.contact_person,
                'phone': client.phone,
                'address': client.address,
                'is_active': client.is_active,
                'api_enabled': bool(client.api_enabled) if client.api_enabled is not None else False,
                'password_change_enabled': bool(client.password_change_enabled) if client.password_change_enabled is not None else False
            }
        
        user_dict = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': user.full_name,
            'role': user.role.value,
            'is_active': user.is_active,
            'created_at': user.created_at,
            'updated_at': user.updated_at,
            'api_enabled': client_data['api_enabled'] if client_data else False,
            'password_change_enabled': client_data['password_change_enabled'] if client_data else False,
            'client': client_data
        }
        user_responses.append(UserResponse.model_validate(user_dict))
    
    return PaginatedResponseBaseSchema.success(
        data=user_responses,
        total=total,
        page=page,
        page_size=page_size
    )


# ==================== 示例2：获取用户详情（使用服务层） ====================
@router.get("/{user_id}", response_model=ResponseBaseSchema[UserResponse], summary="获取用户详情")
async def get_user(
    user_id: int = Path(..., ge=1, description="用户ID"),
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户详情（重构后版本）
    
    重构说明：
    - 权限检查和查询逻辑都在 UserService.get_user_by_id() 中
    - endpoint代码从30行减少到5行
    """
    # 调用服务层（包含权限检查和查询逻辑）
    user = await user_service.get_user_by_id(user_id, current_user, include_client=True)
    
    # 转换为响应模型
    return ResponseBaseSchema.success(data=UserResponse.model_validate(user))


# ==================== 示例3：创建用户（使用服务层） ====================
@router.post("/", response_model=ResponseBaseSchema[UserResponse], summary="创建用户")
async def create_user(
    user_in: UserCreate,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin)
):
    """
    创建用户（重构后版本）
    
    重构说明：
    - 数据验证、权限检查、创建逻辑都在 UserService.create_user() 中
    - 审计日志也在服务层记录
    """
    # 调用服务层
    user = await user_service.create_user(
        user_data=user_in.model_dump(),
        current_user=current_user
    )
    
    # 失效相关缓存
    await CacheInvalidator.invalidate_user_cache(user.id)
    
    return ResponseBaseSchema.success(data=UserResponse.model_validate(user))


# ==================== 示例4：获取用户统计（使用服务层+缓存） ====================
@router.get("/stats", response_model=ResponseBaseSchema[dict], summary="获取用户统计信息")
async def get_user_stats(
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin)
):
    """
    获取用户统计信息（重构后版本）
    
    重构说明：
    - 使用 @cached 装饰器自动缓存结果
    - 业务逻辑在服务层
    """
    # 调用服务层（如果服务层方法使用了@cached装饰器，会自动缓存）
    stats = await user_service.get_user_stats()
    
    return ResponseBaseSchema.success(data=stats)

