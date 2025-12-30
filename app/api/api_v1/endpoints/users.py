"""
用户管理API端点
提供用户信息的CRUD操作，包括：
- 获取用户列表（支持分页和过滤）
- 获取用户详情
- 创建新用户（支持管理员和客户角色）
- 更新用户信息
- 删除用户（检查关联数据）
- 仅管理员可访问
"""
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
from io import BytesIO
from urllib.parse import quote
import pandas as pd

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.audit_log import log_create, log_update, log_delete, log_activate, log_deactivate
from app.models.models import User, UserRole, Client, Publisher
from app.schemas.user import UserCreate, UserUpdate, UserResponse, PasswordChange
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
import uuid
from fastapi import Request

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
        page_size: int = Query(10, ge=1, le=100, description="每页条数"),
        username: str | None = Query(None, description="用户名过滤"),
        role: str | None = Query(None, description="角色过滤"),
        status: str | None = Query(None, description="状态过滤: active/inactive")
):
    """
    获取用户列表，支持分页和过滤
    - 仅管理员可访问
    - 支持按用户名、角色和状态过滤
    - 返回分页用户列表
    - 根据设备类型自动优化分页大小
    """
    # ====== 设备类型优化：自动调整分页大小 ======
    from app.core.utils import optimize_page_size_for_device
    page_size = optimize_page_size_for_device(request, page_size, default_page_size=10)
    # ====== 构建查询 ======
    query = select(User)

    # 用户名搜索（优先使用全文搜索，回退到LIKE）
    if username:
        from app.core.fulltext_search import search_with_fulltext
        query = await search_with_fulltext(
            db=db,
            model_class=User,
            search_fields=["username", "full_name", "email"],
            search_term=username,
            base_query=query,
            use_fulltext=True
        )

    # 角色精确匹配（处理空字符串）
    role_filter = None
    if role and role.strip():  # 如果role存在且不是空字符串
        try:
            role_filter = UserRole(role)  # 尝试转换为枚举
        except ValueError:
            # 如果不是有效的枚举值，忽略该过滤条件
            logger.warning(f"Invalid role filter value: {role}")
            role_filter = None

    if role_filter:
        query = query.where(User.role == role_filter)

    # 状态过滤（处理空字符串）
    status_filter = None
    if status and status.strip():  # 如果status存在且不是空字符串
        if status.lower() == 'active':
            status_filter = True
        elif status.lower() == 'inactive':
            status_filter = False

    if status_filter is not None:
        query = query.where(User.is_active == status_filter)

    # ====== 计算分页参数 ======
    offset = (page - 1) * page_size

    # ====== 执行查询获取总数 ======
    # 使用func.count()提高性能和准确性（比查询所有数据再计数快）
    count_query = select(func.count(User.id))
    # 用户名搜索（优先使用全文搜索，回退到LIKE）
    if username:
        from app.core.fulltext_search import search_with_fulltext
        count_query = await search_with_fulltext(
            db=db,
            model_class=User,
            search_fields=["username", "full_name", "email"],
            search_term=username,
            base_query=count_query,
            use_fulltext=True
        )
    if role_filter:
        count_query = count_query.where(User.role == role_filter)
    if status_filter is not None:
        count_query = count_query.where(User.is_active == status_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0  # 如果为None，返回0

    result = await db.execute(query.order_by(User.id).offset(offset).limit(page_size))
    users = result.scalars().unique().all()

    # 批量获取客户信息（避免N+1查询）
    # 先收集所有客户角色的用户ID
    client_user_ids = [user.id for user in users if user.role == UserRole.CLIENT]
    client_map = {}
    if client_user_ids:
        try:
            client_query = select(Client).where(Client.user_id.in_(client_user_ids))
            client_result = await db.execute(client_query)
            clients = client_result.scalars().all()
            client_map = {client.user_id: client for client in clients}
        except Exception as e:
            logger.error(f"查询客户信息失败: {str(e)}", exc_info=True)
            # 如果查询失败，继续执行，只是没有客户信息
            client_map = {}

    # 转换为响应模型并添加客户信息
    user_responses = []
    for user in users:
        # 获取客户信息（如果用户是客户角色）
        client_data = None
        api_enabled = False
        password_change_enabled = False
        if user.role == UserRole.CLIENT:
            client = client_map.get(user.id)
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
        # ====== 缓存优化 ======
        from app.core.cache import get_cached, set_cached, generate_cache_key
        cache_key = generate_cache_key("user_stats")
        cached = await get_cached(cache_key)
        if cached:
            logger.debug("缓存命中: user_stats")
            return ResponseBaseSchema.success(data=cached)
        
        # 总用户数
        total_result = await db.execute(select(func.count(User.id)))
        total_users = total_result.scalar() or 0

        # 按角色统计
        admin_result = await db.execute(
            select(func.count(User.id)).where(User.role == UserRole.ADMIN)
        )
        admin_count = admin_result.scalar() or 0

        client_result = await db.execute(
            select(func.count(User.id)).where(User.role == UserRole.CLIENT)
        )
        client_count = client_result.scalar() or 0

        # 按状态统计
        active_result = await db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        active_count = active_result.scalar() or 0

        inactive_result = await db.execute(
            select(func.count(User.id)).where(User.is_active == False)
        )
        inactive_count = inactive_result.scalar() or 0

        # 有客户信息的用户数
        client_users_result = await db.execute(
            select(func.count(func.distinct(Client.user_id)))
        )
        client_users_count = client_users_result.scalar() or 0

        stats_data = {
            "total_users": total_users,
            "by_role": {
                "admin": admin_count,
                "client": client_count
            },
            "by_status": {
                "active": active_count,
                "inactive": inactive_count
            },
            "with_client_info": client_users_count
        }
        
        # 缓存结果（缓存 5 分钟）
        await set_cached(cache_key, stats_data, ttl=300)
        
        return ResponseBaseSchema.success(data=stats_data)
    except Exception as e:
        logger.error(f"获取用户统计信息失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取用户统计信息失败：{str(e)}。请稍后重试或联系管理员"
        )


@router.get("/export/excel", response_class=StreamingResponse, summary="导出用户数据")
async def export_users_excel(
        username: str | None = Query(None, description="用户名过滤"),
        role: str | None = Query(None, description="角色过滤"),
        status: str | None = Query(None, description="状态过滤: active/inactive"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    导出用户数据到Excel文件
    - 仅管理员可访问
    - 支持按用户名、角色和状态过滤
    - 返回Excel文件流
    """
    # 构建查询（与get_users相同的逻辑）
    query = select(User)

    if username:
        query = query.where(func.lower(User.username).like(f"%{username.lower()}%"))

    role_filter = None
    if role and role.strip():
        try:
            role_filter = UserRole(role)
        except ValueError:
            logger.warning(f"Invalid role filter value: {role}")
            role_filter = None

    if role_filter:
        query = query.where(User.role == role_filter)

    status_filter = None
    if status and status.strip():
        if status.lower() == 'active':
            status_filter = True
        elif status.lower() == 'inactive':
            status_filter = False

    if status_filter is not None:
        query = query.where(User.is_active == status_filter)

    # 获取所有用户数据
    result = await db.execute(query.order_by(User.id))
    users = result.scalars().unique().all()

    # 如果没有数据，抛出错误提示用户
    if not users:
        from app.core.exceptions import raise_api_exception
        from app.core.errors import ErrorCode
        raise_api_exception(
            error_code=ErrorCode.NOT_FOUND,
            message="无数据，不能导出",
            detail="当前筛选条件下没有可导出的用户数据，请调整筛选条件后重试"
        )

    # 获取所有客户用户的ID
    client_user_ids = [user.id for user in users if user.role == UserRole.CLIENT]

    # 批量获取客户信息
    client_map = {}
    if client_user_ids:
        try:
            client_query = select(Client).where(Client.user_id.in_(client_user_ids))
            client_result = await db.execute(client_query)
            clients = client_result.scalars().all()
            client_map = {client.user_id: client for client in clients}
        except Exception as e:
            logger.error(f"查询客户信息失败: {str(e)}", exc_info=True)
            # 如果查询失败，继续执行，只是没有客户信息
            client_map = {}

    # 准备导出数据
    data = []
    for user in users:
        client = client_map.get(user.id) if user.role == UserRole.CLIENT else None

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

    # 创建Excel文件
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = pd.DataFrame(data)
        df.to_excel(writer, index=False, sheet_name="用户数据")

        # 设置列宽自适应
        worksheet = writer.sheets["用户数据"]
        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value)) for cell in column_cells) if column_cells else 0
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 50)

    output.seek(0)
    from app.core.utils import get_app_now_naive
    filename = f"用户数据_{get_app_now_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"
    encoded_filename = quote(filename.encode('utf-8'))

    logger.info(f"User data exported by {current_user.username}, total: {len(data)} users")

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/me", response_model=ResponseBaseSchema[UserResponse], summary="获取当前用户信息")
async def get_current_user_info(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    获取当前登录用户的详细信息
    - 需要认证（任何已登录用户都可以访问）
    - 返回当前用户的完整信息，包括客户信息（如果用户是客户角色）
    """
    # 获取关联的客户信息（如果用户是客户角色）- 使用selectinload预加载
    from sqlalchemy.orm import selectinload
    from sqlalchemy import and_
    
    query = select(User).options(selectinload(User.clients)).where(User.id == current_user.id)
    result = await db.execute(query)
    user = result.scalars().unique().first()
    
    if not user:
        raise_api_exception(
            ErrorCode.UNAUTHORIZED,
            detail="用户不存在"
        )
    
    client_data = None
    api_enabled = False
    password_change_enabled = False
    has_publisher = False
    if user.role == UserRole.CLIENT:
        # 客户信息已通过selectinload预加载，直接访问
        client = user.clients[0] if user.clients else None
        if client:
            api_enabled = client.api_enabled  # 获取API开关状态
            password_change_enabled = client.password_change_enabled  # 获取密码修改开关状态
            
            # 检查该客户是否有关联的渠道（只检查激活的渠道）
            publisher_check = await db.execute(
                select(func.count(Publisher.id)).where(
                    and_(
                        Publisher.client_id == client.id,
                        Publisher.is_active == True
                    )
                )
            )
            publisher_count = publisher_check.scalar() or 0
            has_publisher = publisher_count > 0
            
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
    user_data = UserResponse.model_validate(user_dict).model_dump()

    return ResponseBaseSchema.success(data=user_data)


@router.put("/me/password", response_model=ResponseBaseSchema[dict], summary="修改当前用户密码")
async def change_password(
        request: Request,
        password_data: PasswordChange,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    修改当前登录用户的密码
    - 需要认证（任何已登录用户都可以访问）
    - 需要验证当前密码
    - 只能修改自己的密码
    - 客户角色需要检查password_change_enabled开关
    """
    # 如果是客户角色，检查是否允许修改密码 - 使用selectinload预加载
    if current_user.role == UserRole.CLIENT:
        from sqlalchemy.orm import selectinload
        query = select(User).options(selectinload(User.clients)).where(User.id == current_user.id)
        result = await db.execute(query)
        user = result.scalars().unique().first()
        client = user.clients[0] if user and user.clients else None
        if client and not client.password_change_enabled:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="客户密码修改功能已被管理员禁用，请联系管理员修改密码"
            )
    
    # 验证当前密码
    if not current_user.verify_password(password_data.old_password):
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail="当前密码不正确，请重新输入"
        )

    # 验证新密码强度
    from app.core.validation import validate_password_strength
    is_valid, error_msg = validate_password_strength(password_data.new_password)
    if not is_valid:
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail=f"新密码验证失败：{error_msg}"
        )

    # 检查新密码是否与当前密码相同
    if current_user.verify_password(password_data.new_password):
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail="新密码不能与当前密码相同"
        )

    # 更新密码
    current_user.hashed_password = current_user.get_password_hash(password_data.new_password)

    # 保存到数据库
    try:
        await db.commit()
        await db.refresh(current_user)
    except Exception as e:
        await db.rollback()
        logger.error(f"修改密码失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"修改密码失败：{str(e)}。请稍后重试或联系管理员"
        )

    logger.info(f"User {current_user.username} changed password")

    # 记录操作日志
    await log_update(
        db=db,
        user=current_user,
        resource_type="USER",
        resource_id=current_user.id,
        resource_name=current_user.username,
        request=request,
        details={"action": "change_password"}
    )

    return ResponseBaseSchema.success(data={"message": "密码修改成功"})


@router.get("/{user_id}", response_model=ResponseBaseSchema[UserResponse], summary="获取用户详情")
async def get_user(
        request: Request,
        user_id: int = Path(..., ge=1, description="用户ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取指定用户的详细信息
    - 仅管理员可访问
    - 返回用户完整信息，包括客户信息（如果用户是客户角色）
    - 使用selectinload预加载客户信息，避免N+1查询
    """
    # 使用selectinload预加载客户信息，避免N+1查询
    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(User).options(selectinload(User.clients)).where(User.id == user_id)
    )
    user = result.scalars().unique().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    # 获取关联的客户信息（如果用户是客户角色）- 客户信息已通过selectinload预加载
    client_data = None
    api_enabled = False
    password_change_enabled = False
    if user.role == UserRole.CLIENT:
        # 客户信息已通过selectinload预加载，直接访问
        client = user.clients[0] if user.clients else None
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
    from app.core.validation import validate_username, validate_email, validate_password_strength

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

    # ====== 唯一性检查 ======
    # 优化：一次性检查用户名和邮箱是否存在，减少查询次数
    from sqlalchemy import or_
    conditions = [User.username == user_in.username]
    if user_in.email:
        conditions.append(User.email == user_in.email)
    
    result = await db.execute(select(User).where(or_(*conditions)))
    existing_users = result.scalars().all()
    
    # 检查用户名是否已存在
    username_exists = any(user.username == user_in.username for user in existing_users)
    if username_exists:
        raise_api_exception(
            ErrorCode.USERNAME_TAKEN,
            detail=f"用户名 '{user_in.username}' 已被使用，请选择其他用户名"
        )

    # 检查邮箱是否已存在
    if user_in.email:
        email_exists = any(user.email == user_in.email for user in existing_users)
        if email_exists:
            raise_api_exception(
                ErrorCode.EMAIL_TAKEN,
                detail=f"邮箱 '{user_in.email}' 已被使用，请使用其他邮箱地址"
            )

    # 创建用户对象
    user = User(
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        role=user_in.role,
        is_active=user_in.is_active if user_in.is_active is not None else True,
        login_restricted=user_in.login_restricted if user_in.login_restricted is not None else False,
        login_message=user_in.login_message
    )

    # 设置密码
    user.hashed_password = user.get_password_hash(user_in.password)

    # 保存到数据库（使用事务确保数据一致性）
    try:
        db.add(user)
        # 先刷新用户对象以获取 user.id（flush 但不提交，仍在同一事务中）
        await db.flush()
        await db.refresh(user)

        # 如果提供了客户信息，同时创建客户（在同一事务中）
        if user_in.company_name:
            # 检查该用户是否已有客户关联 - 优化：只查询是否存在
            result = await db.execute(select(func.count(Client.id)).where(Client.user_id == user.id))
            client_exists = (result.scalar() or 0) > 0
            if client_exists:
                logger.warning(f"User {user.username} already has a client associated")
            else:
                # 创建客户对象（在同一事务中，此时 user.id 已经有值）
                client = Client(
                    user_id=user.id,  # 现在 user.id 已经有值了
                    key=str(uuid.uuid4()),  # 生成UUID作为key字段的默认值
                    company_name=user_in.company_name,
                    contact_person=user_in.contact_person,
                    phone=user_in.phone,
                    address=user_in.address,
                    is_active=user_in.is_active if user_in.is_active is not None else True
                )
                db.add(client)

        # 一次性提交所有更改
        await db.commit()
        await db.refresh(user)

        # 如果创建了客户，刷新客户对象以获取完整信息（包括key）
        if user_in.company_name:
            # 优化：使用selectinload预加载客户信息，避免额外查询
            from sqlalchemy.orm import selectinload
            user_query = select(User).options(selectinload(User.clients)).where(User.id == user.id)
            user_result = await db.execute(user_query)
            user_with_clients = user_result.scalars().unique().first()
            if user_with_clients and user_with_clients.clients:
                client = user_with_clients.clients[0]
                await db.refresh(client)
            logger.info(f"User {user.username} and client created successfully")
    except Exception as e:
        await db.rollback()
        logger.error(f"创建用户失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建用户失败：{str(e)}。请检查数据格式或联系管理员"
        )

    logger.info(f"User {user.username} created by {current_user.username}")

    # 记录创建操作
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

    # 确保 role 转换为字符串
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
    if user_in.company_name:
        result = await db.execute(select(Client).where(Client.user_id == user.id))
        client = result.scalars().first()
        if client:
            user_dict['client'] = {
                'id': client.id,
                'key': client.key,  # 包含API密钥
                'company_name': client.company_name,
                'contact_person': client.contact_person,
                'phone': client.phone,
                'address': client.address,
                'is_active': client.is_active
            }

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
    更新用户信息
    - 仅管理员可访问
    - 可更新用户角色、状态和登录限制
    - 支持密码更新
    """
    # 获取用户
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise_api_exception(
            ErrorCode.USER_NOT_FOUND,
            detail=f"用户ID {user_id} 不存在"
        )

    # 获取更新数据（排除未设置的字段）
    update_data = user_in.model_dump(exclude_unset=True)

    # 防止修改自己为非管理员
    if user.id == current_user.id and "role" in update_data:
        role_value = update_data.get("role")
        if role_value and role_value != UserRole.ADMIN.value:
            raise_api_exception(
                ErrorCode.CANNOT_MODIFY_SELF_ROLE,
                detail="不能将自己的角色修改为非管理员。如需修改角色，请联系其他管理员操作"
            )

    # 优化：一次性检查新用户名和邮箱是否存在，减少查询次数
    from sqlalchemy import or_
    conditions = []
    new_username = None
    new_email = None
    
    if "username" in update_data and update_data.get("username") != user.username:
        new_username = update_data.get("username")
        if new_username:
            conditions.append(User.username == new_username)
    
    if "email" in update_data and update_data.get("email") != user.email:
        new_email = update_data.get("email")
        if new_email:
            conditions.append(User.email == new_email)
    
    if conditions:
        result = await db.execute(select(User).where(or_(*conditions)))
        existing_users = result.scalars().all()
        
        # 检查用户名是否已存在（如果修改了用户名）
        if new_username:
            username_exists = any(u.username == new_username for u in existing_users)
            if username_exists:
                raise_api_exception(
                    ErrorCode.USERNAME_TAKEN,
                    detail=f"用户名 '{new_username}' 已被使用，请选择其他用户名"
                )

    # 检查邮箱是否已存在（如果修改了邮箱）
        if new_email:
            email_exists = any(u.email == new_email for u in existing_users)
            if email_exists:
                raise_api_exception(
                    ErrorCode.EMAIL_TAKEN,
                    detail=f"邮箱 '{new_email}' 已被使用，请使用其他邮箱地址"
                )

    # 如果更新密码
    if "password" in update_data and update_data["password"]:
        user.hashed_password = user.get_password_hash(update_data["password"])
        del update_data["password"]

    # 处理 role 字段（如果是字符串，需要转换为枚举）
    if "role" in update_data and update_data["role"]:
        role_value = update_data["role"]
        if isinstance(role_value, str):
            try:
                update_data["role"] = UserRole(role_value)
            except ValueError:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"无效的角色值：{role_value}。支持的角色：admin, client"
                )

    # 检查 is_active 是否改变（用于记录激活/禁用日志）
    old_is_active = user.is_active
    is_active_changed = False

    # 更新其他字段
    for key, value in update_data.items():
        if hasattr(user, key):
            if key == "is_active" and value != old_is_active:
                is_active_changed = True
            setattr(user, key, value)

    # 保存到数据库
    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        logger.error(f"更新用户失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新用户失败：{str(e)}。请检查数据格式或联系管理员"
        )

    logger.info(f"User {user.username} updated by {current_user.username}")

    # 如果 is_active 改变，记录激活/禁用日志
    if is_active_changed:
        if user.is_active:
            await log_activate(
                db=db,
                user=current_user,
                resource_type="USER",
                resource_id=user.id,
                resource_name=user.username,
                request=request
            )
        else:
            await log_deactivate(
                db=db,
                user=current_user,
                resource_type="USER",
                resource_id=user.id,
                resource_name=user.username,
                request=request
            )

    # 记录更新操作（排除 is_active，因为已经单独记录）
    update_data = user_in.model_dump(exclude_unset=True)
    # 移除敏感信息
    if "password" in update_data:
        update_data["password"] = "***"
    # 如果只更新了 is_active，不记录 UPDATE 日志（避免重复）
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

    # 确保 role 转换为字符串
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
    return ResponseBaseSchema.success(data=UserResponse.model_validate(user_dict))


@router.delete("/{user_id}", response_model=ResponseBaseSchema[dict], summary="删除用户")
async def delete_user(
        request: Request,
        user_id: int = Path(..., ge=1, description="用户ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    删除用户
    - 仅管理员可访问
    - 检查用户是否存在关联客户数据
    - 永久删除用户
    """
    # 防止删除自己
    if user_id == current_user.id:
        raise_api_exception(
            ErrorCode.CANNOT_DELETE_SELF,
            detail="不能删除自己的账户。如需删除，请联系其他管理员操作"
        )

    # 获取用户
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise_api_exception(
            ErrorCode.USER_NOT_FOUND,
            detail=f"用户ID {user_id} 不存在"
        )

    # 检查是否有关联客户
    result = await db.execute(select(Client).where(Client.user_id == user_id))
    clients = result.scalars().all()
    if clients:
        raise_api_exception(
            ErrorCode.USER_HAS_CLIENTS,
            detail=f"无法删除用户，该用户关联了 {len(clients)} 个客户数据。请先删除或转移关联的客户数据"
        )

    # 删除用户
    try:
        await db.delete(user)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"删除用户失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除用户失败：{str(e)}。请稍后重试或联系管理员"
        )

    logger.info(f"User {user.username} deleted by {current_user.username}")

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

    return ResponseBaseSchema.success(data={"message": "用户已成功删除"})
