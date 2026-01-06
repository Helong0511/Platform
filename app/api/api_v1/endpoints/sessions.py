"""
用户会话管理API端点
提供会话查看、强制退出等功能
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.config import settings
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.core.utils import get_app_now_naive
from app.models.models import User, UserRole
from app.models.session import UserSession, TokenBlacklist
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from pydantic import BaseModel

# 创建路由实例
router = APIRouter()
logger = logging.getLogger(__name__)


# ====== Schema定义 ======
class SessionResponse(BaseModel):
    """会话响应模型"""
    id: int
    user_id: int
    token_jti: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_info: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    last_activity: datetime
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class BlacklistResponse(BaseModel):
    """黑名单响应模型"""
    id: int
    token_jti: str
    user_id: int
    username: Optional[str] = None  # 用户名（可选）
    revoked_at: datetime
    expires_at: datetime
    reason: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/me/sessions", response_model=PaginatedResponseBaseSchema[list[SessionResponse]], summary="获取当前用户的活跃会话")
async def get_my_sessions(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数")
):
    """
    获取当前用户的活跃会话列表（已重构使用服务层）
    - 用户可以查看自己的所有会话
    - 返回分页结果
    """
    # 使用服务层（业务逻辑在SessionService中）
    from app.core.dependencies import get_session_service
    from app.services.session_service import SessionService
    
    session_service: SessionService = await get_session_service(db)
    
    # 调用服务层获取当前用户的会话列表（服务层会处理查询、分页）
    sessions, total = await session_service.get_my_sessions(
        user_id=current_user.id,
        page=page,
        page_size=page_size
    )
    
    # 转换为响应格式
    session_responses = [SessionResponse.model_validate(session) for session in sessions]
    
    return PaginatedResponseBaseSchema.success(
        data=session_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/me/sessions/{session_id}/revoke", response_model=ResponseBaseSchema[dict], summary="撤销指定会话")
async def revoke_my_session(
        request: Request,
        session_id: int = Path(..., ge=1, description="会话ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    撤销当前用户的指定会话（已重构使用服务层）
    - 用户只能撤销自己的会话
    - 将token加入黑名单
    - 标记会话为非活跃
    """
    # 使用服务层（业务逻辑在SessionService中）
    from app.core.dependencies import get_session_service
    from app.services.session_service import SessionService
    
    session_service: SessionService = await get_session_service(db)
    
    # 调用服务层撤销会话（服务层会处理验证、黑名单、标记等）
    await session_service.revoke_my_session(session_id, current_user.id, current_user)
    
    # 记录审计日志
    try:
        from app.core.audit_log import log_user_action
        await log_user_action(
            db=db,
            action_type="REVOKE_SESSION",
            user=current_user,
            resource_type="SESSION",
            resource_id=session_id,
            resource_name=f"会话 {session_id}",
            request=request,
            success=True
        )
    except Exception as e:
        logger.warning(f"记录审计日志失败: {e}")
    
    return ResponseBaseSchema.success(
        data={"message": "会话已撤销"},
        message="会话已撤销"
    )


@router.post("/me/sessions/revoke-all", response_model=ResponseBaseSchema[dict], summary="撤销当前用户的所有其他会话")
async def revoke_all_my_sessions(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    撤销当前用户的所有其他会话（保留当前会话，已重构使用服务层）
    - 获取当前请求的token jti
    - 将所有其他会话的token加入黑名单
    - 标记所有其他会话为非活跃
    """
    # 使用服务层（业务逻辑在SessionService中）
    from app.core.dependencies import get_session_service
    from app.services.session_service import SessionService
    
    session_service: SessionService = await get_session_service(db)
    
    # 获取当前token的jti
    from app.core.config import settings
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    current_jti = None
    
    if token:
        try:
            from jose import jwt
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"],
                options={"verify_exp": False}
            )
            current_jti = payload.get("jti")
        except Exception:
            pass
    
    # 调用服务层撤销所有其他会话（服务层会处理查询、黑名单、标记等）
    revoked_count = await session_service.revoke_all_my_sessions(
        user_id=current_user.id,
        current_jti=current_jti,
        current_user=current_user
    )
    
    # 记录审计日志
    try:
        from app.core.audit_log import log_user_action
        await log_user_action(
            db=db,
            action_type="REVOKE_ALL_SESSIONS",
            user=current_user,
            resource_type="SESSION",
            resource_name=f"撤销了 {revoked_count} 个会话",
            request=request,
            success=True
        )
    except Exception as e:
        logger.warning(f"记录审计日志失败: {e}")
    
    return ResponseBaseSchema.success(
        data={"message": f"已撤销 {revoked_count} 个会话", "revoked_count": revoked_count},
        message=f"已撤销 {revoked_count} 个会话"
    )


@router.get("/users/{user_id}/sessions", response_model=PaginatedResponseBaseSchema[list[SessionResponse]], summary="获取指定用户的会话（管理员）")
async def get_user_sessions(
        request: Request,
        user_id: int = Path(..., ge=1, description="用户ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数")
):
    """
    获取指定用户的活跃会话列表（仅管理员，已重构使用服务层）
    """
    # 使用服务层（业务逻辑在SessionService中）
    from app.core.dependencies import get_session_service
    from app.services.session_service import SessionService
    
    session_service: SessionService = await get_session_service(db)
    
    # 调用服务层获取指定用户的会话列表（服务层会处理用户验证、查询、分页）
    sessions, total = await session_service.get_user_sessions(
        user_id=user_id,
        page=page,
        page_size=page_size
    )
    
    # 转换为响应格式
    session_responses = [SessionResponse.model_validate(session) for session in sessions]
    
    return PaginatedResponseBaseSchema.success(
        data=session_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/users/{user_id}/sessions/{session_id}/revoke", response_model=ResponseBaseSchema[dict], summary="撤销指定用户的会话（管理员）")
async def revoke_user_session(
        request: Request,
        user_id: int = Path(..., ge=1, description="用户ID"),
        session_id: int = Path(..., ge=1, description="会话ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    撤销指定用户的指定会话（仅管理员，已重构使用服务层）
    """
    # 使用服务层（业务逻辑在SessionService中）
    from app.core.dependencies import get_session_service
    from app.services.session_service import SessionService
    
    session_service: SessionService = await get_session_service(db)
    
    # 调用服务层撤销用户会话（服务层会处理验证、黑名单、标记等）
    await session_service.revoke_user_session(user_id, session_id, current_user)
    
    # 记录审计日志
    try:
        from app.core.audit_log import log_user_action
        await log_user_action(
            db=db,
            action_type="REVOKE_SESSION",
            user=current_user,
            resource_type="SESSION",
            resource_id=session_id,
            resource_name=f"用户 {user_id} 的会话 {session_id}",
            request=request,
            success=True
        )
    except Exception as e:
        logger.warning(f"记录审计日志失败: {e}")
    
    return ResponseBaseSchema.success(
        data={"message": "会话已撤销"},
        message="会话已撤销"
    )


@router.post("/users/{user_id}/sessions/revoke-all", response_model=ResponseBaseSchema[dict], summary="撤销指定用户的所有会话（管理员）")
async def revoke_all_user_sessions(
        request: Request,
        user_id: int = Path(..., ge=1, description="用户ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    撤销指定用户的所有会话（仅管理员，已重构使用服务层）
    """
    # 使用服务层（业务逻辑在SessionService中）
    from app.core.dependencies import get_session_service
    from app.services.session_service import SessionService
    
    session_service: SessionService = await get_session_service(db)
    
    # 调用服务层撤销用户所有会话（服务层会处理用户验证、查询、黑名单、标记等）
    revoked_count, username = await session_service.revoke_all_user_sessions(user_id, current_user)
    
    # 记录审计日志
    try:
        from app.core.audit_log import log_user_action
        await log_user_action(
            db=db,
            action_type="REVOKE_ALL_SESSIONS",
            user=current_user,
            resource_type="SESSION",
            resource_id=user_id,
            resource_name=f"用户 {username} 的所有会话（{revoked_count}个）",
            request=request,
            success=True
        )
    except Exception as e:
        logger.warning(f"记录审计日志失败: {e}")
    
    return ResponseBaseSchema.success(
        data={"message": f"已撤销用户 {username} 的 {revoked_count} 个会话", "revoked_count": revoked_count},
        message=f"已撤销 {revoked_count} 个会话"
    )


@router.get("/blacklist", response_model=PaginatedResponseBaseSchema[list[BlacklistResponse]], summary="获取Token黑名单列表（管理员）")
async def get_blacklist(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        user_id: Optional[int] = Query(None, ge=1, description="用户ID（可选，筛选指定用户的黑名单）")
):
    """
    获取Token黑名单列表（仅管理员）
    - 可以查看所有已撤销的Token
    - 支持按用户ID筛选
    - 返回分页结果
    """
    # 构建查询，关联用户表获取用户名
    from sqlalchemy.orm import selectinload
    
    query = select(TokenBlacklist, User.username).join(
        User, TokenBlacklist.user_id == User.id, isouter=True
    )
    
    # 如果指定了用户ID，添加筛选条件
    if user_id:
        query = query.where(TokenBlacklist.user_id == user_id)
    
    # 按撤销时间倒序排列
    query = query.order_by(TokenBlacklist.revoked_at.desc())
    
    # 获取总数
    count_query = select(func.count()).select_from(TokenBlacklist)
    if user_id:
        count_query = count_query.where(TokenBlacklist.user_id == user_id)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页查询
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    rows = result.all()
    
    # 转换为响应格式，包含用户名
    blacklist_responses = []
    for blacklist_item, username in rows:
        blacklist_dict = {
            "id": blacklist_item.id,
            "token_jti": blacklist_item.token_jti,
            "user_id": blacklist_item.user_id,
            "username": username,
            "revoked_at": blacklist_item.revoked_at,
            "expires_at": blacklist_item.expires_at,
            "reason": blacklist_item.reason
        }
        blacklist_responses.append(BlacklistResponse(**blacklist_dict))
    
    return PaginatedResponseBaseSchema.success(
        data=blacklist_responses,
        total=total,
        page=page,
        page_size=page_size
    )

