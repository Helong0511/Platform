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


@router.get("/me/sessions", response_model=PaginatedResponseBaseSchema[list[SessionResponse]], summary="获取当前用户的活跃会话")
async def get_my_sessions(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=100, description="每页条数")
):
    """
    获取当前用户的活跃会话列表
    - 用户可以查看自己的所有会话
    - 返回分页结果
    """
    # 构建查询
    query = select(UserSession).where(
        UserSession.user_id == current_user.id,
        UserSession.expires_at > datetime.now(timezone.utc)  # 只返回未过期的会话
    )
    count_query = select(func.count(UserSession.id)).where(
        UserSession.user_id == current_user.id,
        UserSession.expires_at > datetime.now(timezone.utc)
    )
    
    # 获取总数
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 应用分页和排序
    query = query.order_by(UserSession.last_activity.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # 执行查询
    result = await db.execute(query)
    sessions = result.scalars().all()
    
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
    撤销当前用户的指定会话
    - 用户只能撤销自己的会话
    - 将token加入黑名单
    - 标记会话为非活跃
    """
    # 查询会话
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == current_user.id
        )
    )
    session = result.scalars().first()
    
    if not session:
        raise_api_exception(
            ErrorCode.NOT_FOUND,
            detail="会话不存在或不属于当前用户"
        )
    
    # 将token加入黑名单
    blacklist_entry = TokenBlacklist(
        token_jti=session.token_jti,
        user_id=current_user.id,
        expires_at=session.expires_at,
        reason="用户主动撤销会话"
    )
    db.add(blacklist_entry)
    
    # 标记会话为非活跃
    session.is_active = False
    
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
    撤销当前用户的所有其他会话（保留当前会话）
    - 获取当前请求的token jti
    - 将所有其他会话的token加入黑名单
    - 标记所有其他会话为非活跃
    """
    # 获取当前token的jti
    from fastapi.security import HTTPBearer
    from app.core.security import oauth2_scheme
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
    
    # 查询所有其他活跃会话
    query = select(UserSession).where(
        UserSession.user_id == current_user.id,
        UserSession.is_active == True,
        UserSession.expires_at > datetime.now(timezone.utc)
    )
    if current_jti:
        query = query.where(UserSession.token_jti != current_jti)
    
    result = await db.execute(query)
    sessions = result.scalars().all()
    
    revoked_count = 0
    for session in sessions:
        # 将token加入黑名单
        blacklist_entry = TokenBlacklist(
            token_jti=session.token_jti,
            user_id=current_user.id,
            expires_at=session.expires_at,
            reason="用户撤销所有其他会话"
        )
        db.add(blacklist_entry)
        
        # 标记会话为非活跃
        session.is_active = False
        revoked_count += 1
    
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
        page_size: int = Query(10, ge=1, le=100, description="每页条数")
):
    """
    获取指定用户的活跃会话列表（仅管理员）
    """
    # 优化：直接在查询会话时验证用户存在性，避免额外查询
    # 构建查询 - 使用JOIN验证用户存在性（如果用户不存在，会话查询将返回空结果）
    query = select(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.expires_at > datetime.now(timezone.utc)
    )
    
    # 先执行一次查询检查用户是否存在（如果会话查询返回空，可能是用户不存在或没有会话）
    # 为了区分这两种情况，先检查用户是否存在
    user_result = await db.execute(select(User.id).where(User.id == user_id))
    user_exists = user_result.scalar() is not None
    
    if not user_exists:
        raise_api_exception(
            ErrorCode.USER_NOT_FOUND,
            detail=f"用户ID {user_id} 不存在"
        )
    count_query = select(func.count(UserSession.id)).where(
        UserSession.user_id == user_id,
        UserSession.expires_at > datetime.now(timezone.utc)
    )
    
    # 获取总数
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 应用分页和排序
    query = query.order_by(UserSession.last_activity.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # 执行查询
    result = await db.execute(query)
    sessions = result.scalars().all()
    
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
    撤销指定用户的指定会话（仅管理员）
    """
    # 查询会话
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id
        )
    )
    session = result.scalars().first()
    
    if not session:
        raise_api_exception(
            ErrorCode.NOT_FOUND,
            detail="会话不存在"
        )
    
    # 将token加入黑名单
    blacklist_entry = TokenBlacklist(
        token_jti=session.token_jti,
        user_id=user_id,
        expires_at=session.expires_at,
        reason=f"管理员 {current_user.username} 强制撤销"
    )
    db.add(blacklist_entry)
    
    # 标记会话为非活跃
    session.is_active = False
    
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
    撤销指定用户的所有会话（仅管理员）
    """
    # 检查用户是否存在
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    
    if not user:
        raise_api_exception(
            ErrorCode.USER_NOT_FOUND,
            detail=f"用户ID {user_id} 不存在"
        )
    
    # 查询所有活跃会话
    query = select(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.is_active == True,
        UserSession.expires_at > datetime.now(timezone.utc)
    )
    
    result = await db.execute(query)
    sessions = result.scalars().all()
    
    revoked_count = 0
    for session in sessions:
        # 将token加入黑名单
        blacklist_entry = TokenBlacklist(
            token_jti=session.token_jti,
            user_id=user_id,
            expires_at=session.expires_at,
            reason=f"管理员 {current_user.username} 强制撤销所有会话"
        )
        db.add(blacklist_entry)
        
        # 标记会话为非活跃
        session.is_active = False
        revoked_count += 1
    
    # 记录审计日志
    try:
        from app.core.audit_log import log_user_action
        await log_user_action(
            db=db,
            action_type="REVOKE_ALL_SESSIONS",
            user=current_user,
            resource_type="SESSION",
            resource_id=user_id,
            resource_name=f"用户 {user.username} 的所有会话（{revoked_count}个）",
            request=request,
            success=True
        )
    except Exception as e:
        logger.warning(f"记录审计日志失败: {e}")
    
    return ResponseBaseSchema.success(
        data={"message": f"已撤销用户 {user.username} 的 {revoked_count} 个会话", "revoked_count": revoked_count},
        message=f"已撤销 {revoked_count} 个会话"
    )

