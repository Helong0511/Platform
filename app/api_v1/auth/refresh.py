"""令牌刷新 API

职责：校验 refresh_token，重新签发 access_token 与 refresh_token 对。

权限：无需登录，但 refresh_token 须有效且用户未被禁用/限制登录。

主要端点：POST /auth/refresh。

安全特性：
- 优先从 HttpOnly Cookie 读取 refresh_token
- 兼容旧客户端 Body 传 refresh_token（Cookie 缺失时回退）
- 失败时清除无效 Cookie
"""
import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.auth_response import (
    auth_failure_response,
    build_token_json_response,
    raise_auth_error,
)
from app.core.auth_user_payload import build_auth_user_payload
from app.core.config import settings
from app.core.audit_log import log_user_action
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.security import JWTUtils
from app.models.models import User, UserRole, Publisher
from app.schemas.auth import RefreshTokenRequest

router = APIRouter()
logger = logging.getLogger(__name__)


def _resolve_refresh_token(request: Request, token_data: Optional[RefreshTokenRequest]) -> Optional[str]:
    """Cookie 优先；Body 兼容旧集成。"""
    cookie_token = request.cookies.get("refresh_token")
    if cookie_token and cookie_token.strip():
        return cookie_token.strip()
    if token_data and token_data.refresh_token and token_data.refresh_token.strip():
        return token_data.refresh_token.strip()
    return None


@router.post("/refresh", summary="刷新访问令牌")
async def refresh_token(
        request: Request,
        token_data: Optional[RefreshTokenRequest] = Body(default=None),
        db: AsyncSession = Depends(get_db),
):
    """
    使用刷新令牌获取新的访问令牌。

    - 优先：HttpOnly Cookie `refresh_token`
    - 兼容：JSON Body `{"refresh_token":"..."}`（外部脚本 / 旧版客户端）
    - 成功：新令牌写入 Cookie，响应体仅含 user
    - 失败：清除无效 Cookie 并返回 401/403
    """
    try:
        refresh_token_value = _resolve_refresh_token(request, token_data)
        if not refresh_token_value:
            raise_auth_error(
                ErrorCode.TOKEN_INVALID,
                "未找到刷新令牌，请重新登录",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        payload = await JWTUtils.verify_token(refresh_token_value, db=db)

        if payload.get("type") != "refresh":
            raise_auth_error(
                ErrorCode.TOKEN_INVALID,
                "无效的刷新令牌",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        user_id = payload.get("sub")
        if not user_id:
            raise_auth_error(
                ErrorCode.TOKEN_INVALID,
                "无法从令牌中获取用户ID",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        result = await db.execute(
            select(User)
            .options(selectinload(User.clients))
            .where(User.id == int(user_id))
        )
        user = result.scalars().first()

        if not user:
            raise_auth_error(
                ErrorCode.USER_NOT_FOUND,
                "用户不存在",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            raise_auth_error(
                ErrorCode.USER_DISABLED,
                "用户已被禁用",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        if user.login_restricted:
            raise_auth_error(
                ErrorCode.FORBIDDEN,
                user.login_message or "登录已被限制",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        new_access_token = JWTUtils.create_access_token(
            user.id, expires_delta=access_token_expires
        )
        new_refresh_token = JWTUtils.create_refresh_token(
            user.id, expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )

        api_enabled = False
        has_publisher = False
        client_record = None
        if user.role == UserRole.CLIENT and user.clients:
            client_record = user.clients[0]
            if client_record:
                api_enabled = bool(client_record.api_enabled)
                publisher_check = await db.execute(
                    select(func.count(Publisher.id)).where(
                        and_(
                            Publisher.client_id == client_record.id,
                            Publisher.is_active == True,
                        )
                    )
                )
                has_publisher = (publisher_check.scalar() or 0) > 0

        user_payload = build_auth_user_payload(
            user,
            api_enabled=api_enabled,
            has_publisher=has_publisher,
            client=client_record,
        )

        logger.info(f"用户 {user.username} 刷新令牌成功")
        await log_user_action(
            db=db,
            action_type="LOGIN",
            user=user,
            resource_type="SESSION",
            resource_id=user.id,
            resource_name=user.username,
            request=request,
            details={"action": "refresh_token"},
        )
        return build_token_json_response(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            user=user_payload,
            message="令牌刷新成功",
        )

    except HTTPException as exc:
        return auth_failure_response(exc)
    except Exception as e:
        logger.error(f"刷新令牌失败: {str(e)}", exc_info=True)
        try:
            raise_auth_error(
                ErrorCode.TOKEN_INVALID,
                "刷新令牌失败，请重新登录",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )
        except HTTPException as exc:
            return auth_failure_response(exc)
