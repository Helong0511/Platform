"""用户认证API端点模块

功能说明：
提供用户登录和身份验证相关的所有API端点，包括：
- 用户登录：验证用户名密码，生成JWT访问令牌
- 用户登出：清除会话和令牌
- 获取当前用户信息：验证令牌并返回用户信息
- 刷新令牌：延长令牌有效期

安全特性：
- 密码使用bcrypt加密存储和验证
- JWT令牌使用RS256算法（非对称加密）或HS256算法（对称加密）
- 支持IP白名单验证（客户角色）
- 登录限制检查（login_restricted字段）
- 登录失败记录和审计日志

认证流程：
1. 用户提交用户名和密码
2. 验证用户是否存在且密码正确
3. 检查用户状态（is_active, login_restricted）
4. 检查IP白名单（仅客户角色）
5. 生成JWT访问令牌
6. 返回令牌和用户信息

令牌管理：
- 访问令牌：用于API请求认证，默认240分钟有效期
- 令牌存储在客户端（localStorage或cookie）
- 令牌包含用户ID、角色等基本信息
- 令牌过期后需要重新登录

注意事项：
1. 登录接口使用OAuth2PasswordRequestForm格式（username/password）
2. 所有需要认证的接口都需要在请求头中携带Bearer令牌
3. 客户角色的IP白名单验证：127.0.0.1始终允许
4. 登录失败不会暴露具体原因（用户名不存在或密码错误都返回相同错误）。

说明：用户认证，含登录、刷新令牌、登出及 JWT 校验。"""
import logging
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.audit_log import log_login, log_logout, commit_audit_log
from app.core.auth_response import build_token_json_response, clear_auth_cookies, raise_auth_error
from app.core.auth_user_payload import build_auth_user_payload
from app.core.async_orm import get_first_loaded_collection_item
from app.core.config import settings
from app.core.errors import ErrorCode
from app.core.database import get_db
from app.core.security import JWTUtils, get_current_user
from app.core.utils import get_client_ip
from app.models.models import User, UserRole, Publisher
from app.services.session_service import record_access_token_session, revoke_tokens_from_request
from app.schemas.auth import LoginResponse
from app.schemas.base import ResponseBaseSchema

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


async def _record_login_failure(
        db: AsyncSession,
        request: Request,
        *,
        error_message: str,
        user: User | None = None,
        username: str | None = None,
) -> None:
    """记录登录失败审计日志，失败时不影响登录流程（详见字段 Field description）。"""
    try:
        await log_login(
            db=db,
            request=request,
            user=user,
            username=username,
            success=False,
            error_message=error_message,
        )
        await commit_audit_log(db)
    except Exception as e:
        logger.warning(f"记录登录失败审计日志失败: {e}")


@router.post("/login", response_model=LoginResponse, summary="用户登录", tags=["认证管理"])
async def login(
        request: Request,
        db: AsyncSession = Depends(get_db),
        form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    用户登录接口
    
    功能说明：
    验证用户凭据（用户名和密码），验证通过后生成JWT访问令牌并返回用户信息
    
    请求格式：
    - Content-Type: application/x-www-form-urlencoded（OAuth2标准格式）
    - 参数：
      - username: 用户名（必填）
      - password: 密码（必填）
    
    验证流程：
    1. 根据用户名查询用户
    2. 验证密码是否正确（使用bcrypt验证）
    3. 检查用户是否激活（is_active）
    4. 检查用户是否被限制登录（login_restricted）
    5. 如果是客户角色，验证IP白名单
    6. 生成JWT访问令牌
    7. 记录登录日志（审计日志）
    
    安全特性：
    - 密码验证使用安全的bcrypt算法
    - 登录失败不暴露具体原因（防止用户名枚举攻击）
    - 客户IP白名单验证（仅客户角色）
    - 127.0.0.1始终允许（本地访问）
    - 所有登录尝试都记录到审计日志
    
    响应内容：
    - access_token: JWT访问令牌（用于后续API请求）
    - token_type: 令牌类型（固定为"bearer"）
    - user: 用户基本信息（ID、用户名、角色等）
    - unread_notifications: 未读通知数量（仅管理员）
    
    Args:
        request: FastAPI请求对象，用于获取客户端IP等信息
        db: 数据库会话（依赖注入）
        form_data: OAuth2密码请求表单，包含username和password
    
    Returns:
        LoginResponse: 登录响应对象，包含访问令牌和用户信息
    
    Raises:
        HTTPException: 
            - 401: 用户名或密码错误
            - 403: 用户被禁用或限制登录
            - 403: IP不在白名单中（仅客户角色）
    
    Example:
        # 使用curl测试
        curl -X POST "http://localhost:8000/api/v1/auth/login" \
             -H "Content-Type: application/x-www-form-urlencoded" \
             -d "username=admin&password=admin123"
        
        # 响应示例
        {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "user": {
                "id": 1,
                "username": "admin",
                "role": "admin",
                ...
            },
            "unread_notifications": 5
        }
    """
    # 注意：请求基本信息已由 RequestLoggingMiddleware 记录，这里只记录登录相关的关键信息
    client_ip = get_client_ip(request)

    # 只在开发环境记录详细请求头（生产环境可能包含敏感信息）
    if not settings.is_production:
        logger.debug(f"登录请求 - 方法: {request.method}, 路径: {request.url.path}, IP: {client_ip}")

    # ====== 查询用户 ======
    # 根据用户名查询用户（使用用户名而不是ID，因为登录时只有用户名）
    # 优化：如果是客户角色，同时加载客户信息，减少后续查询

    try:
        result = await db.execute(
            select(User)
            .options(selectinload(User.clients))
            .where(User.username == form_data.username)
        )
        user = result.scalars().first()

        # ====== 验证凭据 ======
        # 检查用户是否存在以及密码是否正确（使用安全的密码验证方法）
        if not user:
            logger.warning(f"用户登录失败: 用户不存在, 用户名={form_data.username}, IP={client_ip}")
            await _record_login_failure(
                db, request,
                username=form_data.username,
                error_message="用户名或密码不正确",
            )
            raise_auth_error(
                ErrorCode.INVALID_CREDENTIALS,
                "用户名或密码不正确",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.verify_password(form_data.password):
            logger.warning(f"用户登录失败: 密码错误, 用户名={form_data.username}, IP={client_ip}")
            await _record_login_failure(
                db, request,
                user=user,
                error_message="用户名或密码不正确",
            )
            raise_auth_error(
                ErrorCode.INVALID_CREDENTIALS,
                "用户名或密码不正确",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )
    except HTTPException:
        raise
    except Exception as e:
        # 捕获其他异常，记录日志并返回401错误
        error_msg = str(e)
        error_type = type(e).__name__
        logger.error(
            f"登录过程中发生异常: {error_type}: {error_msg}, "
            f"用户名={form_data.username if form_data else 'unknown'}, "
            f"IP={client_ip}",
            exc_info=True
        )
        # 在开发环境返回更详细的错误信息，生产环境返回通用错误
        if settings.is_development:
            detail = f"登录失败: {error_type}: {error_msg}"
        else:
            detail = "登录失败，请稍后重试"
        raise_auth_error(
            ErrorCode.INVALID_CREDENTIALS,
            detail,
            http_status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        logger.warning(f"用户登录失败: 用户已被禁用, 用户名={form_data.username}, IP={client_ip}")
        await _record_login_failure(
            db, request,
            user=user,
            error_message="用户已被禁用",
        )
        raise_auth_error(
            ErrorCode.USER_DISABLED,
            "用户已被禁用",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    if user.login_restricted:
        logger.warning(f"用户登录失败: 登录受限, 用户名={form_data.username}, IP={client_ip}")
        await _record_login_failure(
            db, request,
            user=user,
            error_message=user.login_message or "登录已被限制",
        )
        raise_auth_error(
            ErrorCode.FORBIDDEN,
            user.login_message or "登录已被限制",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    # ====== 客户IP白名单检查 ======
    # 只有客户角色需要检查IP白名单，管理员不受限制
    # 127.0.0.1和localhost始终允许（本地访问）
    if user.role == UserRole.CLIENT:
        # 127.0.0.1和localhost始终允许
        local_ips = ["127.0.0.1", "localhost", "::1"]
        if client_ip not in local_ips:
            # 优化：客户信息已在查询用户时通过selectinload加载，直接使用
            client = get_first_loaded_collection_item(user, "clients")

            if client:
                # 检查IP白名单
                allowed_ips = client.allowed_ips
                if allowed_ips and allowed_ips.strip():
                    # 解析IP白名单（支持逗号分隔）
                    allowed_ip_list = [ip.strip() for ip in allowed_ips.split(",") if ip.strip()]
                    if allowed_ip_list and client_ip not in allowed_ip_list:
                        logger.warning(
                            f"客户登录失败: IP不在白名单中, "
                            f"用户名={form_data.username}, IP={client_ip}, "
                            f"白名单={allowed_ips}"
                        )
                        await _record_login_failure(
                            db, request,
                            user=user,
                            error_message=f"IP地址 {client_ip} 不在允许列表中",
                        )
                        raise_auth_error(
                            ErrorCode.FORBIDDEN,
                            f"IP地址 {client_ip} 不在允许列表中，请联系管理员",
                            http_status=status.HTTP_403_FORBIDDEN,
                        )
                # 如果allowed_ips为空或None，则不限制IP（向后兼容）

    # ====== 生成访问令牌和刷新令牌 ======
    # 创建JWT访问令牌，设置过期时间（从配置中读取）
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = JWTUtils.create_access_token(
        user.id, expires_delta=access_token_expires
    )

    refresh_token = JWTUtils.create_refresh_token(
        user.id, expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )

    # ====== 记录会话信息 ======
    await record_access_token_session(
        db,
        user_id=user.id,
        access_token=access_token,
        request=request,
        access_token_expires=access_token_expires,
    )

    logger.info(f"User {user.username} logged in successfully")

    # ====== 返回响应 ======
    # 如果是客户角色，获取客户的api_enabled和has_publisher信息
    api_enabled = False
    has_publisher = False
    client_record = get_first_loaded_collection_item(user, "clients")
    if user.role == UserRole.CLIENT and client_record:
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

    try:
        await log_login(db=db, user=user, request=request, success=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"记录登录日志失败: {e}")

    return build_token_json_response(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_payload,
        message="登录成功",
    )


@router.post("/logout", summary="用户退出登录")
async def logout(
        request: Request,
        response: Response,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    用户退出登录接口
    - 记录退出登录操作到审计日志
    - 清除 HttpOnly Cookie 中的 access_token 和 refresh_token
    - 使令牌立即失效
    
    功能：用户登出（logout）。
    实现：异步端点，通过 Service 层访问数据库/缓存。
    鉴权：由 Depends(get_current_user) 或 require_admin 控制访问范围。
    响应：统一 ResponseBaseSchema / PaginatedResponseBaseSchema 包装。
    """
    try:
        await revoke_tokens_from_request(
            db=db,
            request=request,
            user_id=current_user.id,
            reason="用户退出登录",
        )
        # 记录退出登录日志
        await log_logout(db=db, user=current_user, request=request)
        # 注意：这里不commit，由get_db的finally块自动commit

        logger.info(f"User {current_user.username} logged out successfully")

        clear_auth_cookies(response)

        return ResponseBaseSchema.success(data={"message": "退出登录成功"})
    except HTTPException:
        raise
    except Exception as e:
        # 日志记录失败不应该影响退出登录
        logger.warning(f"记录退出登录日志失败: {e}")

        clear_auth_cookies(response)
        
        return ResponseBaseSchema.success(data={"message": "退出登录成功"})
