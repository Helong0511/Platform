"""
客户管理API端点
提供客户信息的CRUD操作，包括：
- 获取客户列表（支持分页和过滤）
- 获取客户详情
- 创建新客户（支持创建新用户或关联已有用户）
- 更新客户信息
- 删除客户（检查关联数据）
"""
# Python 3.10+ 使用内置类型注解
import logging
import re
import uuid
from io import BytesIO
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.audit_log import (
    log_create, log_update, log_delete, log_activate, log_deactivate,
    log_user_action, commit_audit_log,
)
from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.dependencies import get_client_service
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.fulltext_search import search_with_fulltext
from app.core.security import require_admin, require_admin_or_self
from app.core.utils import get_app_now_naive
from app.models.models import User, Client, UserRole, Product
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


# 快速更新客户开关的请求模型
class ClientSwitchUpdate(BaseModel):
    """快速更新客户开关的请求模型"""
    api_enabled: bool | None = None
    password_change_enabled: bool | None = None


@router.get("/", response_model=PaginatedResponseBaseSchema[list[ClientResponse]], summary="获取客户列表")
async def get_clients(
        request: Request,
        client_service=Depends(get_client_service),
        current_user: User = Depends(require_admin),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        company_name: str | None = Query(None, description="公司名称过滤"),
        is_active: bool | None = Query(None, description="是否激活过滤")
):
    """
    获取客户列表，支持分页和过滤
    - 仅管理员可访问
    - 支持按公司名称和激活状态过滤
    - 返回分页结果
    """
    clients, total = await client_service.list_clients(
        page=page,
        page_size=page_size,
        company_name=company_name,
        is_active=is_active,
    )

    client_responses = []
    for client in clients:
        client_dict = ClientResponse.model_validate(client).model_dump()
        if client.user:
            client_dict["user_full_name"] = client.user.full_name
        client_responses.append(ClientResponse.model_validate(client_dict))

    return PaginatedResponseBaseSchema.success(
        data=client_responses,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{client_id}", response_model=ResponseBaseSchema[ClientResponse], summary="获取客户详情")
async def get_client(
        client_id: int = Path(..., ge=1, description="客户ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin_or_self)
):
    """
    获取客户详细信息
    - 管理员可以查看所有客户
    - 客户用户只能查看自己的客户信息
    - 返回客户完整信息，包括关联的用户信息
    """
    # 构建查询 - 使用JOIN避免N+1查询问题
    query = select(Client).options(selectinload(Client.user)).where(Client.id == client_id)

    # 如果是客户用户，只能查看自己的客户信息
    if current_user.role == UserRole.CLIENT:
        query = query.where(Client.user_id == current_user.id)

    result = await db.execute(query)
    client = result.scalars().first()

    if not client:
        raise_api_exception(
            ErrorCode.CLIENT_NOT_FOUND,
            detail=f"客户ID {client_id} 不存在或您没有权限访问"
        )

    # 用户信息已通过selectinload预加载，直接访问
    user = client.user

    # 构建响应数据
    client_data = {
        'id': client.id,
        'key': client.key,
        'company_name': client.company_name,
        'contact_person': client.contact_person,
        'phone': client.phone,
        'address': client.address,
        'allowed_ips': client.allowed_ips,
        'is_active': client.is_active,
        'api_enabled': client.api_enabled,
        'password_change_enabled': client.password_change_enabled,
        'created_at': client.created_at,
        'updated_at': client.updated_at,
        'user_id': client.user_id,
        'user_name': user.username if user else None
    }

    return ResponseBaseSchema.success(data=client_data)


@router.post("/", response_model=ResponseBaseSchema[ClientResponse], summary="创建客户")
async def create_client(
        request: Request,
        client_in: ClientCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    创建新客户
    - 仅管理员可访问
    - 如果提供user_id，则关联到已存在的用户账号（clients.user_id 对应 users.id）
    - 如果不提供user_id但提供用户信息（username, password, email），则先创建用户再创建客户
    - 创建客户基本信息
    - 验证用户存在性和唯一性
    """
    try:
        user = None
        user_created = False

        # ====== 用户处理逻辑 ======
        # 情况1：提供了user_id，关联已有用户（当前已废弃，仅保留代码兼容性）
        if client_in.user_id:
            result = await db.execute(select(User).where(User.id == client_in.user_id))
            user = result.scalars().first()

            if not user:
                raise_api_exception(
                    ErrorCode.USER_NOT_FOUND,
                    detail=f"指定的用户ID {client_in.user_id} 不存在，请确认用户是否存在"
                )
        # 情况2：未提供user_id，但提供了用户信息，创建新用户（当前默认模式）
        elif client_in.username and client_in.password and client_in.email:
            # 优化：一次性检查用户名和邮箱是否存在，减少查询次数
            result = await db.execute(
                select(User).where(
                    (User.username == client_in.username) | (User.email == client_in.email)
                )
            )
            existing_users = result.scalars().all()

            # 检查用户名是否已存在
            username_exists = any(user.username == client_in.username for user in existing_users)
            if username_exists:
                raise_api_exception(
                    ErrorCode.USERNAME_TAKEN,
                    detail=f"用户名 '{client_in.username}' 已被使用，请使用其他用户名"
                )

            # 检查邮箱是否已存在
            email_exists = any(user.email == client_in.email for user in existing_users)
            if email_exists:
                raise_api_exception(
                    ErrorCode.EMAIL_TAKEN,
                    detail=f"邮箱 '{client_in.email}' 已被使用，请使用其他邮箱地址"
                )

            # 创建新用户
            user = User(
                username=client_in.username,
                email=client_in.email,
                full_name=client_in.full_name,
                role=UserRole.CLIENT,
                is_active=True
            )
            user.hashed_password = user.get_password_hash(client_in.password)
            db.add(user)
            await db.flush()  # 获取用户ID
            user_created = True
            logger.info(f"创建新用户: {user.username} (ID: {user.id})")
        else:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="创建客户时必须提供用户信息（username, password, email）或user_id"
            )

        # ====== 创建客户 ======
        # 生成唯一的UUID作为客户密钥
        client_key = str(uuid.uuid4())

        # 创建客户对象
        client = Client(
            user_id=user.id,
            key=client_key,
            company_name=client_in.company_name,
            contact_person=client_in.contact_person,
            phone=client_in.phone,
            address=client_in.address,
            allowed_ips=client_in.allowed_ips,
            is_active=client_in.is_active if client_in.is_active is not None else True,
            api_enabled=client_in.api_enabled if client_in.api_enabled is not None else False,
            password_change_enabled=client_in.password_change_enabled if client_in.password_change_enabled is not None else False
        )

        db.add(client)
        # 注意：不需要手动提交事务，get_db 依赖会自动处理
        # 刷新对象以获取最新数据（在自动提交之前）
        await db.flush()
        await db.refresh(client)

        logger.info(f"创建客户: {client.company_name} (ID: {client.id}), 关联用户: {user.username} (ID: {user.id})")

        # 记录创建日志
        await log_create(
            db=db,
            user=current_user,
            resource_type="CLIENT",
            resource_id=client.id,
            resource_name=client.company_name,
            request=request,
            details={
                "user_id": user.id,
                "user_created": user_created,
                "company_name": client.company_name
            }
        )

        return ResponseBaseSchema.success(data=ClientResponse.model_validate(client))
    except HTTPException:
        raise

    except Exception as e:
        # 注意：不需要手动回滚事务，get_db 依赖会自动处理
        logger.error(f"创建客户失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建客户失败：{str(e)}。请检查数据格式或联系管理员"
        )


@router.put("/{client_id}", response_model=ResponseBaseSchema[ClientResponse], summary="更新客户")
async def update_client(
        request: Request,
        client_id: int = Path(..., ge=1, description="客户ID"),
        *,
        client_in: ClientUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    更新客户信息
    - 仅管理员可访问
    - 可更新客户联系信息和状态
    - 支持关联用户变更
    """
    # 获取客户
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalars().first()

    if not client:
        raise_api_exception(
            ErrorCode.CLIENT_NOT_FOUND,
            detail=f"客户ID {client_id} 不存在"
        )

    # 如果变更了关联用户
    if client_in.user_id and client_in.user_id != client.user_id:
        # 检查新用户是否存在
        result = await db.execute(select(User).where(User.id == client_in.user_id))
        new_user = result.scalars().first()
        if not new_user:
            raise_api_exception(
                ErrorCode.USER_NOT_FOUND,
                detail=f"指定的用户ID {client_in.user_id} 不存在，请确认用户是否存在"
            )

        # 检查新用户是否已有客户关联
        result = await db.execute(select(Client).where(Client.user_id == client_in.user_id))
        existing_client = result.scalars().first()
        if existing_client and existing_client.id != client_id:
            raise_api_exception(
                ErrorCode.CLIENT_ALREADY_EXISTS,
                detail=f"用户ID {client_in.user_id} 已关联客户：{existing_client.company_name}。每个用户只能关联一个客户，请选择其他用户"
            )

    # 更新客户信息
    update_data = client_in.model_dump(exclude_unset=True)

    # 如果更新了key字段，需要验证
    if 'key' in update_data and update_data['key']:
        new_key = update_data['key'].strip()
        # 验证UUID格式（简单验证，36个字符，包含连字符）
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if not re.match(uuid_pattern, new_key, re.IGNORECASE):
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="UUID格式不正确，请使用有效的UUID格式（例如：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx）"
            )

        # 检查key是否已被其他客户使用
        if new_key != client.key:
            result = await db.execute(select(Client).where(Client.key == new_key))
            existing_client = result.scalars().first()
            if existing_client:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"UUID '{new_key}' 已被其他客户使用，请使用其他UUID"
                )

    # 检查 is_active 是否改变（用于记录激活/禁用日志）
    old_is_active = client.is_active
    is_active_changed = False

    for key, value in update_data.items():
        if key == "is_active" and value != old_is_active:
            is_active_changed = True
        setattr(client, key, value)

    # 保存到数据库
    try:
        # 注意：不需要手动提交事务，get_db 依赖会自动处理
        # 刷新对象以获取最新数据（在自动提交之前）
        await db.flush()
        await db.refresh(client)
    except HTTPException:
        raise
    except Exception as e:
        # 注意：不需要手动回滚事务，get_db 依赖会自动处理
        logger.error(f"更新客户失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新客户失败：{str(e)}。请检查数据格式或联系管理员"
        )

    logger.info(f"Client {client.company_name} updated by {current_user.username}")

    wrote_audit = False
    if is_active_changed:
        if client.is_active:
            await log_activate(
                db=db,
                user=current_user,
                resource_type="CLIENT",
                resource_id=client_id,
                resource_name=client.company_name,
                request=request
            )
        else:
            await log_deactivate(
                db=db,
                user=current_user,
                resource_type="CLIENT",
                resource_id=client_id,
                resource_name=client.company_name,
                request=request
            )
        wrote_audit = True

    update_data = client_in.model_dump(exclude_unset=True)
    if len(update_data) > 1 or "is_active" not in update_data:
        await log_update(
            db=db,
            user=current_user,
            resource_type="CLIENT",
            resource_id=client_id,
            resource_name=client.company_name,
            request=request,
            details=update_data
        )
        wrote_audit = True

    if wrote_audit:
        await commit_audit_log(db)

    return ResponseBaseSchema.success(data=ClientResponse.model_validate(client))


@router.patch("/{client_id}/switches", response_model=ResponseBaseSchema[ClientResponse], summary="快速更新客户开关")
async def update_client_switches(
        request: Request,
        client_id: int = Path(..., ge=1, description="客户ID"),
        *,
        switch_data: ClientSwitchUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    快速更新客户的API开关和密码修改开关
    - 仅管理员可访问
    - 可以单独更新api_enabled或password_change_enabled，或同时更新两者
    """
    # 获取客户（使用selectinload预加载用户关系，保持与其他端点一致）
    result = await db.execute(
        select(Client).options(selectinload(Client.user)).where(Client.id == client_id)
    )
    client = result.scalars().first()

    if not client:
        raise_api_exception(
            ErrorCode.CLIENT_NOT_FOUND,
            detail=f"客户ID {client_id} 不存在"
        )

    # 更新开关状态
    update_details = {}
    update_values = {}

    if switch_data.api_enabled is not None:
        # 处理 None 值，确保 old_value 是布尔值
        old_value = bool(client.api_enabled) if client.api_enabled is not None else False
        # 确保是布尔值
        new_value = bool(switch_data.api_enabled)
        update_values['api_enabled'] = new_value
        update_details['api_enabled'] = {'old': old_value, 'new': new_value}

    if switch_data.password_change_enabled is not None:
        # 处理 None 值，确保 old_value 是布尔值
        old_value = bool(client.password_change_enabled) if client.password_change_enabled is not None else False
        # 确保是布尔值
        new_value = bool(switch_data.password_change_enabled)
        update_values['password_change_enabled'] = new_value
        update_details['password_change_enabled'] = {'old': old_value, 'new': new_value}

    # 如果没有要更新的值，直接返回
    if not update_values:
        raise_api_exception(
            ErrorCode.VALIDATION_ERROR,
            detail="请至少提供一个要更新的开关值（api_enabled 或 password_change_enabled）"
        )

    # 保存到数据库
    try:
        # 使用 SQLAlchemy 的 update 语句直接更新数据库，确保数据被保存
        stmt = update(Client).where(Client.id == client_id).values(**update_values)
        await db.execute(stmt)

        # 注意：不需要手动提交事务，get_db 依赖会自动处理

        # 重新查询以获取最新数据（使用selectinload预加载用户关系，保持与其他端点一致）
        result = await db.execute(
            select(Client).options(selectinload(Client.user)).where(Client.id == client_id)
        )
        client = result.scalars().first()
        if not client:
            logger.error(f"更新后无法找到客户 {client_id}")
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"更新后无法找到客户ID {client_id}，请刷新页面重试"
            )

        # 刷新对象以获取最新数据（在自动提交之前）
        await db.flush()
        await db.refresh(client)

        # 确保布尔字段不是 None（数据库约束应该保证，但为了安全起见）
        if client.api_enabled is None:
            client.api_enabled = False
        if client.password_change_enabled is None:
            client.password_change_enabled = False
    except HTTPException:
        raise

    except Exception as e:
        # 注意：不需要手动回滚事务，get_db 依赖会自动处理
        # 如果是我们自己的异常，直接抛出
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"更新客户开关失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新客户开关失败：{str(e)}。请检查数据格式或联系管理员"
        )

    logger.info(f"Client {client.company_name} switches updated by {current_user.username}: {update_details}")

    # 记录更新操作
    try:
        await log_update(
            db=db,
            user=current_user,
            resource_type="CLIENT",
            resource_id=client_id,
            resource_name=client.company_name,
            request=request,
            details=update_details
        )
        await commit_audit_log(db)
    except HTTPException:
        raise
    except Exception as log_error:
        logger.warning(f"记录更新日志失败: {str(log_error)}")

    # 确保返回的数据包含最新的开关状态
    try:
        client_data = ClientResponse.model_validate(client)
    except HTTPException:
        raise
    except Exception as validation_error:
        logger.error(f"验证客户响应数据失败: {str(validation_error)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"验证客户数据失败：{str(validation_error)}。请刷新页面重试"
        )

    return ResponseBaseSchema.success(data=client_data)


@router.get("/export", response_class=StreamingResponse, summary="导出客户数据")
async def export_clients_excel(
        request: Request,
        company_name: str | None = Query(None, description="公司名称过滤"),
        is_active: bool | None = Query(None, description="是否激活过滤"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    导出客户数据到Excel文件
    - 仅管理员可访问
    - 支持按公司名称和激活状态过滤
    - 返回Excel文件流
    """
    # 构建查询（与get_clients相同的逻辑）
    query = select(Client).options(selectinload(Client.user))

    # 应用过滤条件
    if company_name:
        # 使用全文搜索（优先）或LIKE查询
        query = await search_with_fulltext(
            db=db,
            model_class=Client,
            search_fields=["company_name", "contact_person"],
            search_term=company_name,
            base_query=query,
            use_fulltext=True
        )

    if is_active is not None:
        query = query.where(Client.is_active == is_active)

    # 获取所有客户数据
    query = query.order_by(Client.id.desc())
    result = await db.execute(query)
    # selectinload不会产生重复行，但为了安全起见使用unique()
    clients = result.unique().scalars().all()

    # 如果没有数据，抛出错误提示用户
    if not clients:
        raise_api_exception(
            error_code=ErrorCode.NOT_FOUND,
            message="无数据，不能导出",
            detail="当前筛选条件下没有可导出的客户数据，请调整筛选条件后重试"
        )

    # 准备导出数据
    data = []
    for client in clients:
        user = client.user
        row = {
            "客户ID": client.id,
            "公司名称": client.company_name or "",
            "联系人": client.contact_person or "",
            "联系电话": client.phone or "",
            "地址": client.address or "",
            "API密钥": client.key or "",
            "允许的IP": client.allowed_ips or "",
            "状态": "启用" if client.is_active else "禁用",
            "API开关": "启用" if client.api_enabled else "禁用",
            "密码修改开关": "启用" if client.password_change_enabled else "禁用",
            "创建时间": client.created_at.strftime("%Y-%m-%d %H:%M:%S") if client.created_at else "",
            "更新时间": client.updated_at.strftime("%Y-%m-%d %H:%M:%S") if client.updated_at else "",
        }

        # 添加用户信息
        if user:
            row.update({
                "用户ID": user.id,
                "用户名": user.username or "",
                "邮箱": user.email or "",
                "全名": user.full_name or "",
            })
        else:
            row.update({
                "用户ID": "",
                "用户名": "",
                "邮箱": "",
                "全名": "",
            })

        data.append(row)

    # 创建Excel文件
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = pd.DataFrame(data)
        df.to_excel(writer, index=False, sheet_name="客户数据")

        # 设置列宽自适应
        worksheet = writer.sheets["客户数据"]
        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value)) for cell in column_cells) if column_cells else 0
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 50)

    output.seek(0)
    filename = f"客户数据_{get_app_now_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"
    encoded_filename = quote(filename.encode('utf-8'))

    logger.info(f"Client data exported by {current_user.username}, total: {len(data)} clients")

    await log_user_action(
        db=db,
        action_type="EXPORT",
        user=current_user,
        resource_type="CLIENT",
        request=request,
        details={"row_count": len(data), "company_name": company_name, "is_active": is_active},
    )
    await commit_audit_log(db)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.delete("/{client_id}", response_model=ResponseBaseSchema[dict], summary="删除客户")
async def delete_client(
        client_id: int = Path(..., ge=1, description="客户ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
        request: Request = None
):
    """
    删除客户
    - 仅管理员可访问
    - 检查是否有关联产品，如果有则不允许删除
    - 删除客户时不会删除关联的用户账号
    """
    # 获取客户
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalars().first()

    if not client:
        raise_api_exception(
            ErrorCode.CLIENT_NOT_FOUND,
            detail=f"客户ID {client_id} 不存在"
        )

    # 检查是否有关联产品 - 优化：只查询数量，不查询所有产品
    product_count_result = await db.execute(
        select(func.count(Product.id)).where(Product.client_id == client_id)
    )
    product_count = product_count_result.scalar() or 0

    if product_count > 0:
        raise_api_exception(
            ErrorCode.CLIENT_HAS_PRODUCTS,
            detail=f"客户 '{client.company_name}' 有关联产品（{product_count}个），无法删除。请先删除或转移所有关联产品"
        )

    # 记录删除日志
    await log_delete(
        db=db,
        user=current_user,
        resource_type="CLIENT",
        resource_id=client_id,
        resource_name=client.company_name,
        request=request
    )

    # 删除客户
    await db.delete(client)
    # 注意：不需要手动提交事务，get_db 依赖会自动处理

    logger.info(f"Client {client.company_name} deleted by {current_user.username}")

    return ResponseBaseSchema.success(data={"message": "客户已成功删除"})
