"""令牌刷新 API

职责：校验 refresh_token，重新签发 access_token 与 refresh_token 对。

权限：无需登录，但 refresh_token 须有效且用户未被禁用/限制登录。

主要端点：POST /auth/refresh。

说明：用户认证，含登录、刷新令牌、登出及 JWT 校验。"""
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.auth_response import build_token_json_response, raise_auth_error
from app.core.auth_user_payload import build_auth_user_payload
from app.core.config import settings
from app.core.audit_log import log_user_action
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.security import JWTUtils
from app.models.models import User, UserRole, Publisher
from app.schemas.auth import LoginResponse, RefreshTokenRequest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/refresh", response_model=LoginResponse, summary="刷新访问令牌")
async def refresh_token(
        request: Request,
        token_data: RefreshTokenRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    使用刷新令牌获取新的访问令牌
    
    功能说明：
    - 验证刷新令牌的有效性
    - 检查用户状态
    - 生成新的访问令牌和刷新令牌
    - 返回新的令牌对
    
    请求格式：
    - Content-Type: application/json
    - Body: {"refresh_token": "..."}
    
    安全特性：
    - 验证刷新令牌签名
    - 检查刷新令牌类型
    - 验证用户状态
    - 支持令牌黑名单（可选）
    
    Args:
        request: FastAPI请求对象
        refresh_token: 刷新令牌字符串
        db: 数据库会话
    
    Returns:
        LoginResponse: 包含新的访问令牌、刷新令牌和用户信息
    
    Raises:
        HTTPException:
            - 401: 刷新令牌无效或过期
            - 403: 用户被禁用或限制登录
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 异常处理 ----------
    try:
        # 从请求体中获取刷新令牌
        refresh_token = token_data.refresh_token

        # 验证刷新令牌
        payload = await JWTUtils.verify_token(refresh_token, db=db)

        # 检查令牌类型
        token_type = payload.get("type")
        # ---------- 条件分支 ----------
        if token_type != "refresh":
            raise_auth_error(
                ErrorCode.TOKEN_INVALID,
                "无效的刷新令牌",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        user_id = payload.get("sub")
        # ---------- 条件分支 ----------
        if not user_id:
            raise_auth_error(
                ErrorCode.TOKEN_INVALID,
                "无法从令牌中获取用户ID",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        # 查询用户（如果是客户角色，同时加载客户信息）
        result = await db.execute(
            select(User)
            .options(selectinload(User.clients))
            .where(User.id == int(user_id))
        )
        user = result.scalars().first()

        # ---------- 条件分支 ----------
        if not user:
            raise_auth_error(
                ErrorCode.USER_NOT_FOUND,
                "用户不存在",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        # ---------- 条件分支 ----------
        if not user.is_active:
            raise_auth_error(
                ErrorCode.USER_DISABLED,
                "用户已被禁用",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        # ---------- 条件分支 ----------
        if user.login_restricted:
            raise_auth_error(
                ErrorCode.FORBIDDEN,
                user.login_message or "登录已被限制",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        # 生成新的访问令牌和刷新令牌
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        new_access_token = JWTUtils.create_access_token(
            user.id, expires_delta=access_token_expires
        )
        new_refresh_token = JWTUtils.create_refresh_token(
            user.id, expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )

        # 获取客户相关信息（如果是客户角色）
        api_enabled = False
        has_publisher = False
        client_record = None
        # ---------- 条件分支 ----------
        if user.role == UserRole.CLIENT and user.clients:
            client_record = user.clients[0]
            # ---------- 条件分支 ----------
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刷新令牌失败: {str(e)}", exc_info=True)
        raise_auth_error(
            ErrorCode.TOKEN_INVALID,
            "刷新令牌失败，请重新登录",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
