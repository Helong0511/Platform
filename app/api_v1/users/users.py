"""用户管理API端点模块

功能说明：
提供用户信息的完整CRUD操作，包括：
- 用户列表查询：支持分页、筛选、搜索
- 用户详情查询：根据ID获取用户详细信息
- 用户创建：创建新用户（管理员或客户角色）
- 用户更新：更新用户信息（包括密码修改）
- 用户删除：删除用户（检查关联数据）
- 用户统计：获取用户统计信息
- 数据导出：导出用户数据为Excel文件

权限控制：
- 所有接口都需要管理员权限（require_admin）
- 用户可以通过/me接口查看和修改自己的信息
- 密码修改需要验证旧密码

功能特性：
1. 分页查询：
   - 支持按用户名、角色、状态筛选
   - 支持全文搜索（用户名、全名、邮箱）
   - 根据设备类型自动优化分页大小
   - 返回标准分页响应格式

2. 用户创建：
   - 验证用户名唯一性
   - 验证邮箱唯一性（如果提供）
   - 自动加密密码（bcrypt）
   - 支持创建管理员或客户角色
   - 记录审计日志

3. 用户更新：
   - 验证用户名唯一性（如果修改）
   - 验证邮箱唯一性（如果修改）
   - 支持激活/禁用用户
   - 支持设置登录限制和提示消息
   - 记录审计日志

4. 用户删除：
   - 检查是否有关联的客户数据
   - 如果有关联数据，不允许删除
   - 记录审计日志

5. 密码修改：
   - 验证旧密码
   - 验证新密码强度
   - 自动加密新密码
   - 记录审计日志

6. 数据导出：
   - 导出为Excel格式
   - 支持筛选条件
   - 包含所有用户字段
   - 自动处理中文文件名

使用场景：
- 管理员管理用户账户
- 用户查看和修改个人信息
- 批量导出用户数据
- 用户统计和分析

注意事项：
1. 所有操作都记录审计日志
2. 密码使用bcrypt加密，无法解密
3. 删除用户前必须检查关联数据
4. 用户名和邮箱必须唯一
5. 客户角色用户只能有一个关联的客户。

说明：REST API 端点，统一 ResponseBaseSchema 响应；鉴权由各端点 Depends 声明。"""
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, Path
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
# Python 3.10+ 使用内置类型注解
import logging
from datetime import datetime
from app.core.excel_io import excel_streaming_response
import uuid

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.audit_log import (
    log_create, log_update, log_delete, log_activate, log_deactivate,
    log_user_action, commit_audit_log,
)
from app.core.constants import MAX_PAGE_SIZE
from app.core.utils import optimize_page_size_for_device, get_app_now_naive
from app.core.dependencies import get_user_service
from app.services.user_service import UserService
from app.core.infrastructure.cache import get_cache_backend
from app.core.validation import validate_username, validate_email, validate_password_strength
from app.models.models import User, UserRole, Client, Publisher
from app.schemas.user import UserCreate, UserUpdate, UserResponse, PasswordChange
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


@router.get("/", response_model=PaginatedResponseBaseSchema[list[UserResponse]], summary="获取用户列表")
async def get_users(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        username: str | None = Query(None, description="用户名过滤"),
        role: str | None = Query(None, description="角色过滤"),
        status: str | None = Query(None, description="状态过滤: active/inactive")
):
    """
    获取用户列表，支持分页和过滤（已重构使用服务层）
    - 仅管理员可访问
    - 支持按用户名、角色和状态过滤
    - 返回分页用户列表
    - 根据设备类型自动优化分页大小
    """
    # ====== 设备类型优化：自动调整分页大小 ======
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)
    
    # 使用服务层（业务逻辑在UserService中）
    user_service: UserService = await get_user_service(db)
    
    # 转换status参数为布尔值（服务层期望布尔值）
    is_active = None
    if status and status.strip():
        if status.lower() == 'active':
            is_active = True
        elif status.lower() == 'inactive':
            is_active = False
    
    # 调用服务层获取用户列表（服务层会处理权限检查、查询和客户信息预加载）
    users, total = await user_service.get_users(
        current_user=current_user,
        page=page,
        page_size=page_size,
        username=username,
        role=role,
        is_active=is_active
    )
    
    # 转换为响应模型并添加客户信息（客户信息已通过selectinload预加载）
    user_responses = []
    for user in users:
        # 获取客户信息（如果用户是客户角色）
        client_data = None
        api_enabled = False
        password_change_enabled = False
        if user.role == UserRole.CLIENT:
            # 客户信息已通过selectinload预加载，直接访问
            client = user.clients[0] if user.clients else None
            if client:
                # 确保从数据库获取最新的开关状态（布尔值）
                api_enabled = bool(client.api_enabled) if client.api_enabled is not None else False
                password_change_enabled = bool(client.password_change_enabled) if client.password_change_enabled is not None else False
                client_data = {
                    'id': client.id,
                    'company_name': client.company_name,
                    'contact_person': client.contact_person,
                    'phone': client.phone,
                    'address': client.address,
                    'is_active': client.is_active,
                    'api_enabled': api_enabled,  # 包含API开关状态（确保是布尔值）
                    'password_change_enabled': password_change_enabled  # 包含密码修改开关状态（确保是布尔值）
                }

        # 构建用户数据（包含客户信息）
        user_dict = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': user.full_name,
            'role': user.role.value if isinstance(user.role, UserRole) else str(user.role),
            'is_active': user.is_active,
            'created_at': user.created_at,
            'updated_at': user.updated_at,
            'api_enabled': api_enabled,  # API开关状态（用于前端菜单显示）
            'password_change_enabled': password_change_enabled,  # 密码修改开关状态
            'client': client_data  # 客户信息（如果存在）
        }
        user_data = UserResponse.model_validate(user_dict).model_dump()
        user_responses.append(user_data)

    return PaginatedResponseBaseSchema.success(
        data=user_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/stats", response_model=ResponseBaseSchema[dict], summary="获取用户统计信息")
async def get_user_stats(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取用户统计信息
    - 仅管理员可访问
    - 返回用户总数、按角色统计、按状态统计等
    - 使用缓存提升性能（缓存 5 分钟）
    """
    try:
        # 使用服务层（业务逻辑在UserService中）
        user_service: UserService = await get_user_service(db)
        
        # 使用缓存（如果服务层方法使用了@cached装饰器，会自动缓存）
        # 这里手动使用缓存，因为服务层方法可能没有装饰器
        cache = await get_cache_backend()
        cache_key = "user_stats"
        
        cached_data = await cache.get(cache_key)
        if cached_data:
            logger.debug("缓存命中: user_stats")
            return ResponseBaseSchema.success(data=cached_data)
        
        # 调用服务层获取统计信息
        stats_data = await user_service.get_user_stats()
        
        # 缓存结果（缓存 5 分钟）
        await cache.set(cache_key, stats_data, ttl=300)
        
        return ResponseBaseSchema.success(data=stats_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户统计信息失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取用户统计信息失败：{str(e)}。请稍后重试或联系管理员"
        )


@router.get("/export/excel", response_class=StreamingResponse, summary="导出用户数据")
async def export_users_excel(
        request: Request,
        username: str | None = Query(None, description="用户名过滤"),
        role: str | None = Query(None, description="角色过滤"),
        status: str | None = Query(None, description="状态过滤: active/inactive"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    导出用户数据到Excel文件（已重构使用服务层）
    - 仅管理员可访问
    - 支持按用户名、角色和状态过滤
    - 返回Excel文件流
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在UserService中）
    user_service: UserService = await get_user_service(db)
    
    # 转换status参数为布尔值（服务层期望布尔值）
    is_active = None
    # ---------- 条件分支 ----------
    if status and status.strip():
        # ---------- 条件分支 ----------
        if status.lower() == 'active':
            is_active = True
        # ---------- 条件分支 ----------
        elif status.lower() == 'inactive':
            is_active = False
    
    # 调用服务层获取所有用户数据（不分页，获取全部数据用于导出）
    # 使用一个很大的page_size来获取所有数据
    users, total = await user_service.get_users(
        current_user=current_user,
        page=1,
        page_size=10000,  # 使用大值获取所有数据
        username=username,
        role=role,
        is_active=is_active
    )

    # 如果没有数据，抛出错误提示用户
    # ---------- 条件分支 ----------
    if not users:
        raise_api_exception(
            error_code=ErrorCode.NOT_FOUND,
            message="无数据，不能导出",
            detail="当前筛选条件下没有可导出的用户数据，请调整筛选条件后重试"
        )

    # 客户信息已通过selectinload预加载，直接访问

    # 准备导出数据（客户信息已通过selectinload预加载）
    data = []
    # ---------- 循环处理 ----------
    for user in users:
        # 客户信息已通过selectinload预加载，直接访问
        client = user.clients[0] if user.role == UserRole.CLIENT and user.clients else None

        row = {
            "用户ID": user.id,
            "用户名": user.username,
            "邮箱": user.email or "",
            "全名": user.full_name or "",
            "角色": "管理员" if user.role == UserRole.ADMIN else "客户",
            "状态": "启用" if user.is_active else "禁用",
            "创建时间": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "",
        }

        # 如果是客户，添加客户信息
        # ---------- 条件分支 ----------
        if client:
            row.update({
                "公司名称": client.company_name or "",
                "联系人": client.contact_person or "",
                "联系电话": client.phone or "",
                "地址": client.address or "",
            })
        else:
            row.update({
                "公司名称": "",
                "联系人": "",
                "联系电话": "",
                "地址": "",
            })

        data.append(row)

    logger.info(f"User data exported by {current_user.username}, total: {len(data)} users")

    await log_user_action(
        db=db,
        action_type="EXPORT",
        user=current_user,
        resource_type="USER",
        request=request,
        details={"row_count": len(data), "username": username, "role": role, "status": status},
    )
    await commit_audit_log(db)

    # ---------- 构建响应 ----------
    return excel_streaming_response(data, "用户数据", "用户数据")


@router.get("/me", response_model=ResponseBaseSchema[UserResponse], summary="获取当前用户信息")
async def get_current_user_info(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取当前登录用户的详细信息（已重构使用服务层）
    - 需要认证（任何已登录用户都可以访问）
    - 返回当前用户的完整信息，包括客户信息（如果用户是客户角色）
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在UserService中）
    user_service: UserService = await get_user_service(db)
    
    # 获取用户信息（服务层会处理权限检查和客户信息预加载）
    user = await user_service.get_user_by_id(current_user.id, current_user, include_client=True)
    
    client_data = None
    api_enabled = False
    password_change_enabled = False
    has_publisher = False
    # ---------- 条件分支 ----------
    if user.role == UserRole.CLIENT:
        # 客户信息已通过selectinload预加载，直接访问
        client = user.clients[0] if user.clients else None
        # ---------- 条件分支 ----------
        if client:
            api_enabled = client.api_enabled  # 获取API开关状态
            password_change_enabled = client.password_change_enabled  # 获取密码修改开关状态
            
            # 检查该客户是否有关联的渠道（只检查激活的渠道）- 使用服务层
            has_publisher = await user_service.check_client_has_publisher(client.id)
            
            client_data = {
                'id': client.id,
                'key': client.key,  # 包含API密钥
                'company_name': client.company_name,
                'contact_person': client.contact_person,
                'phone': client.phone,
                'address': client.address,
                'is_active': client.is_active,
                'api_enabled': client.api_enabled,  # 包含API开关状态
                'password_change_enabled': client.password_change_enabled,  # 包含密码修改开关状态
                'has_publisher': has_publisher  # 是否有关联的渠道
            }

    # 构建用户数据（包含客户信息）- 使用从数据库查询的user对象
    user_dict = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': user.full_name,
        'role': user.role.value if isinstance(user.role, UserRole) else str(user.role),
        'is_active': user.is_active,
        'created_at': user.created_at,
        'updated_at': user.updated_at,
        'api_enabled': api_enabled,  # API开关状态（用于前端菜单显示）
        'password_change_enabled': password_change_enabled,  # 密码修改开关状态
        'has_publisher': has_publisher,  # 是否有关联的渠道（用于前端菜单显示）
        'client': client_data  # 客户信息（如果存在）
    }
    # ---------- 异常处理 ----------
    try:
        user_data = UserResponse.model_validate(user_dict).model_dump()
    except Exception as exc:
        logger.error(
            "当前用户信息序列化失败 user_id=%s: %s",
            current_user.id,
            exc,
            exc_info=True,
        )
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail="用户信息格式异常，请联系管理员检查账号邮箱等字段",
        )

    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data=user_data)


@router.put("/me/password", response_model=ResponseBaseSchema[dict], summary="修改当前用户密码")
async def change_password(
        request: Request,
        password_data: PasswordChange,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    修改当前登录用户的密码（已重构使用服务层）
    - 需要认证（任何已登录用户都可以访问）
    - 需要验证当前密码
    - 只能修改自己的密码
    - 客户角色需要检查password_change_enabled开关
    """
    # 使用服务层（业务逻辑在UserService中）
    user_service: UserService = await get_user_service(db)
    
    # 调用服务层修改密码（服务层会处理所有验证和权限检查）
    await user_service.change_password(
        user_id=current_user.id,
        old_password=password_data.old_password,
        new_password=password_data.new_password,
        current_user=current_user
    )

    return ResponseBaseSchema.success(data={"message": "密码修改成功"})


@router.get("/{user_id}", response_model=ResponseBaseSchema[UserResponse], summary="获取用户详情")
async def get_user(
        request: Request,
        user_id: int = Path(..., ge=1, description="用户ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取指定用户的详细信息（已重构使用服务层）
    - 管理员可访问所有用户，客户只能访问自己的信息
    - 返回用户完整信息，包括客户信息（如果用户是客户角色）
    - 使用服务层，业务逻辑已优化
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在UserService中）
    user_service: UserService = await get_user_service(db)
    user = await user_service.get_user_by_id(user_id, current_user, include_client=True)
    
    # 获取关联的客户信息（如果用户是客户角色）
    client_data = None
    api_enabled = False
    password_change_enabled = False
    # ---------- 条件分支 ----------
    if user.role == UserRole.CLIENT:
        # 客户信息已通过selectinload预加载，直接访问
        client = user.clients[0] if user.clients else None
        # ---------- 条件分支 ----------
        if client:
            api_enabled = client.api_enabled  # 获取API开关状态
            password_change_enabled = client.password_change_enabled  # 获取密码修改开关状态
            client_data = {
                'id': client.id,
                'key': client.key,  # 包含API密钥
                'company_name': client.company_name,
                'contact_person': client.contact_person,
                'phone': client.phone,
                'address': client.address,
                'is_active': client.is_active,
                'api_enabled': client.api_enabled,  # 包含API开关状态
                'password_change_enabled': client.password_change_enabled  # 包含密码修改开关状态
            }

    # 构建用户数据（包含客户信息）
    user_dict = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': user.full_name,
        'role': user.role.value if isinstance(user.role, UserRole) else str(user.role),
        'is_active': user.is_active,
        'created_at': user.created_at,
        'updated_at': user.updated_at,
        'api_enabled': api_enabled,  # API开关状态（用于前端菜单显示）
        'password_change_enabled': password_change_enabled,  # 密码修改开关状态
        'client': client_data  # 客户信息（如果存在）
    }
    user_data = UserResponse.model_validate(user_dict).model_dump()

    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data=user_data)


@router.post("/", response_model=ResponseBaseSchema[UserResponse], summary="创建用户")
async def create_user(
        request: Request,
        user_in: UserCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    创建新用户
    - 仅管理员可访问
    - 支持创建管理员或客户角色
    - 自动生成密码哈希
    """
    # ====== 输入验证 ======
    # 验证用户名格式
    is_valid, error_msg = validate_username(user_in.username)
    if not is_valid:
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=f"用户名验证失败：{error_msg}"
        )

    # 验证邮箱格式
    if user_in.email:
        is_valid, error_msg = validate_email(user_in.email)
        if not is_valid:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail=f"邮箱格式验证失败：{error_msg}"
            )

    # 验证密码强度
    is_valid, error_msg = validate_password_strength(user_in.password)
    if not is_valid:
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=f"密码强度验证失败：{error_msg}"
        )

    # 使用服务层（业务逻辑在UserService中）
    user_service: UserService = await get_user_service(db)
    
    # 准备用户数据（包含客户信息，如果提供）
    user_data = user_in.model_dump()
    if user_in.company_name:
        user_data['company_name'] = user_in.company_name
        user_data['contact_person'] = user_in.contact_person
        user_data['phone'] = user_in.phone
        user_data['address'] = user_in.address
    
    # 调用服务层创建用户（服务层会处理唯一性检查和客户创建）
    user = await user_service.create_user(user_data, current_user)
    
    # 构建响应数据
    user_dict = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': user.full_name,
        'role': user.role.value if isinstance(user.role, UserRole) else str(user.role),
        'is_active': user.is_active,
        'created_at': user.created_at,
        'updated_at': user.updated_at
    }
    
    # 如果创建了客户，添加客户信息到响应中（包括API密钥）
    if user.clients:
        client = user.clients[0]
        user_dict['client'] = {
            'id': client.id,
            'key': client.key,  # 包含API密钥
            'company_name': client.company_name,
            'contact_person': client.contact_person,
            'phone': client.phone,
            'address': client.address,
            'is_active': client.is_active
        }
    
    # 记录创建操作（使用audit_log的log_create函数）
    await log_create(
        db=db,
        user=current_user,
        resource_type="USER",
        resource_id=user.id,
        resource_name=user.username,
        request=request,
        details={
            "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active
        }
    )
    await commit_audit_log(db)

    return ResponseBaseSchema.success(data=UserResponse.model_validate(user_dict))


@router.put("/{user_id}", response_model=ResponseBaseSchema[UserResponse], summary="更新用户")
async def update_user(
        request: Request,
        user_id: int = Path(..., ge=1, description="用户ID"),
        *,
        user_in: UserUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    更新用户信息（已重构使用服务层）
    - 仅管理员可访问
    - 可更新用户角色、状态和登录限制
    - 支持密码更新
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在UserService中）
    user_service: UserService = await get_user_service(db)
    
    # 获取更新数据（排除未设置的字段）
    update_data = user_in.model_dump(exclude_unset=True)

    # 更新前记录 is_active 旧值，用于激活/禁用审计
    user_before = await user_service.get_user_by_id(user_id, current_user, include_client=False)
    old_is_active = user_before.is_active

    # 调用服务层更新用户（服务层会处理所有验证和权限检查）
    user = await user_service.update_user(user_id, update_data, current_user)

    # 记录更新操作
    # ---------- 条件分支 ----------
    if "password" in update_data:
        update_data["password"] = "***"

    wrote_audit = False
    # ---------- 条件分支 ----------
    if "is_active" in update_data and update_data["is_active"] != old_is_active:
        # ---------- 条件分支 ----------
        if user.is_active:
            await log_activate(
                db=db,
                user=current_user,
                resource_type="USER",
                resource_id=user.id,
                resource_name=user.username,
                request=request,
            )
        else:
            await log_deactivate(
                db=db,
                user=current_user,
                resource_type="USER",
                resource_id=user.id,
                resource_name=user.username,
                request=request,
            )
        wrote_audit = True

    # ---------- 条件分支 ----------
    if len(update_data) > 1 or "is_active" not in update_data:
        await log_update(
            db=db,
            user=current_user,
            resource_type="USER",
            resource_id=user.id,
            resource_name=user.username,
            request=request,
            details=update_data
        )
        wrote_audit = True

    # ---------- 条件分支 ----------
    if wrote_audit:
        await commit_audit_log(db)

    # 构建响应数据
    user_dict = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': user.full_name,
        'role': user.role.value if isinstance(user.role, UserRole) else str(user.role),
        'is_active': user.is_active,
        'created_at': user.created_at,
        'updated_at': user.updated_at
    }
    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data=UserResponse.model_validate(user_dict))


@router.delete("/{user_id}", response_model=ResponseBaseSchema[dict], summary="删除用户")
async def delete_user(
        request: Request,
        user_id: int = Path(..., ge=1, description="用户ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    删除用户（已重构使用服务层）
    - 仅管理员可访问
    - 检查用户是否存在关联客户数据
    - 永久删除用户
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 防止删除自己
    # ---------- 条件分支 ----------
    if user_id == current_user.id:
        raise_api_exception(
            ErrorCode.CANNOT_DELETE_SELF,
            detail="不能删除自己的账户。如需删除，请联系其他管理员操作"
        )

    # 使用服务层（业务逻辑在UserService中）
    user_service: UserService = await get_user_service(db)
    
    # 获取用户信息（用于记录删除日志）
    user = await user_service.get_user_by_id(user_id, current_user, include_client=True)
    
    # 记录删除操作（在删除前记录，因为删除后user对象可能无法访问）
    await log_delete(
        db=db,
        user=current_user,
        resource_type="USER",
        resource_id=user.id,
        resource_name=user.username,
        request=request,
        details={
            "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
            "email": user.email
        }
    )
    await commit_audit_log(db)
    
    # 调用服务层删除用户（服务层会检查关联数据）
    await user_service.delete_user(user_id, current_user)

    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data={"message": "用户已成功删除"})
