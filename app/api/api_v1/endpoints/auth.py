"""
用户认证API端点模块

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
4. 登录失败不会暴露具体原因（用户名不存在或密码错误都返回相同错误）
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import JWTUtils, get_current_user
from app.core.utils import get_app_now_naive
from app.models.models import Client, User, UserRole, Publisher
from app.schemas.auth import LoginResponse

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


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
        curl -X POST "http://localhost:8000/api/v1/auth/login" \\
             -H "Content-Type: application/x-www-form-urlencoded" \\
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
    from app.core.utils import get_client_ip
    from app.core.config import settings
    client_ip = get_client_ip(request)
    
    # 只在开发环境记录详细请求头（生产环境可能包含敏感信息）
    if not settings.is_production:
        logger.debug(f"登录请求 - 方法: {request.method}, 路径: {request.url.path}, IP: {client_ip}")

    # ====== 查询用户 ======
    # 根据用户名查询用户（使用用户名而不是ID，因为登录时只有用户名）
    # 优化：如果是客户角色，同时加载客户信息，减少后续查询
    from sqlalchemy.orm import selectinload
    
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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码不正确",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.verify_password(form_data.password):
            logger.warning(f"用户登录失败: 密码错误, 用户名={form_data.username}, IP={client_ip}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码不正确",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        # 重新抛出HTTP异常
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
        import os
        if os.getenv("PRODUCTION_ENV", "").lower() != "production":
            detail = f"登录失败: {error_type}: {error_msg}"
        else:
            detail = "登录失败，请稍后重试"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ====== 用户状态检查 ======
    # 检查用户是否被禁用
    if not user.is_active:
        logger.warning(f"用户登录失败: 用户已被禁用, 用户名={form_data.username}, IP={client_ip}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    # 检查用户登录是否受限（用于临时限制用户登录）
    if user.login_restricted:
        logger.warning(f"用户登录失败: 登录受限, 用户名={form_data.username}, IP={client_ip}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=user.login_message or "登录已被限制",
        )

    # ====== 客户IP白名单检查 ======
    # 只有客户角色需要检查IP白名单，管理员不受限制
    # 127.0.0.1和localhost始终允许（本地访问）
    if user.role == UserRole.CLIENT:
        # 127.0.0.1和localhost始终允许
        local_ips = ["127.0.0.1", "localhost", "::1"]
        if client_ip not in local_ips:
            # 优化：客户信息已在查询用户时通过selectinload加载，直接使用
            client = user.clients[0] if user.clients else None

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
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"IP地址 {client_ip} 不在允许列表中，请联系管理员",
                        )
                # 如果allowed_ips为空或None，则不限制IP（向后兼容）

    # ====== 生成访问令牌 ======
    # 创建JWT令牌，设置过期时间（从配置中读取）
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = JWTUtils.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    
    # ====== 记录会话信息 ======
    # 解析token获取jti
    token_jti = None
    try:
        from jose import jwt
        
        # 根据配置的算法选择密钥
        if settings.JWT_ALGORITHM == "RS256":
            # 使用RS256算法（非对称加密），需要公钥验证
            # 注意：JWTUtils 已在文件顶部导入，不需要重复导入
            public_key = JWTUtils._load_rsa_key(
                settings.RSA_PUBLIC_KEY,
                settings.RSA_PUBLIC_KEY_PATH,
                "public"
            )
            key = public_key
        else:
            # 使用HS256算法（对称加密），使用相同的密钥
            key = settings.SECRET_KEY
        
        payload = jwt.decode(
            access_token,
            key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False}  # 不验证过期时间，只获取jti
        )
        token_jti = payload.get("jti")
    except Exception as e:
        # 会话记录失败不应该影响登录
        logger.warning(f"记录会话信息失败: {e}")
    
    if token_jti:
        # 记录会话到数据库
        from app.models.session import UserSession
        from app.core.utils import get_client_ip, get_device_type
        
        # expires_at 需要保持UTC时间用于比较，但存储时转换为北京时间
        expires_at_utc = datetime.now(timezone.utc) + access_token_expires
        # 转换为北京时间（naive）存储到数据库
        from app.core.utils import APP_TIMEZONE
        expires_at = expires_at_utc.astimezone(APP_TIMEZONE).replace(tzinfo=None)
        
        device_type_str = get_device_type(request)
        user_agent = request.headers.get("User-Agent", "")[:500]
        
        session = UserSession(
            user_id=user.id,
            token_jti=token_jti,
            ip_address=client_ip,
            user_agent=user_agent,
            device_info=device_type_str,
            is_active=True,
            last_activity=get_app_now_naive(),  # 使用北京时间
            expires_at=expires_at  # 已转换为北京时间
        )
        db.add(session)
        # 不在这里commit，由get_db的finally块自动commit

    logger.info(f"User {user.username} logged in successfully")

    # ====== 返回响应 ======
    # 如果是客户角色，获取客户的api_enabled和has_publisher信息
    api_enabled = False
    has_publisher = False
    if user.role == UserRole.CLIENT and user.clients:
        # 客户用户：获取第一个客户的api_enabled状态
        client = user.clients[0]
        if client:
            api_enabled = client.api_enabled
            
            # 检查该客户是否有关联的渠道（只检查激活的渠道）
            from sqlalchemy import func, and_
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

    response_data = {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.value,
            "api_enabled": api_enabled,  # 客户API访问开关状态
            "has_publisher": has_publisher  # 是否有关联的渠道（用于前端菜单显示）
        }
    }

    # ====== 设置 HttpOnly Cookie (安全增强) ======
    from fastapi import Response
    # 创建响应对象并设置 Cookie
    # 我们仍然通过 JSON 返回 token 以保持向后兼容，但通过 Cookie 提供更高的安全性
    response = Response()
    # 转换为 JSONResponse 格式以包含数据
    from fastapi.responses import JSONResponse
    json_response = JSONResponse(content=response_data)
    
    # 设置 Cookie
    # httponly=True 防止 XSS 攻击读取 token
    # secure=True 仅允许通过 HTTPS 发送
    # samesite="Lax" 提供基本的 CSRF 防御
    json_response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.is_production,  # 生产环境必须为 True
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    # 异步记录登录日志（不阻塞响应）
    try:
        from app.core.audit_log import log_login
        await log_login(db=db, user=user, request=request, success=True)
    except Exception as e:
        logger.warning(f"记录登录日志失败: {e}")

    return json_response


@router.post("/logout", summary="用户退出登录")
async def logout(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    用户退出登录接口
    - 记录退出登录操作到审计日志
    - 注意：JWT是无状态的，这里主要是记录日志
    - 实际的token失效由前端清除，或等待token过期
    """
    try:
        # 记录退出登录日志
        from app.core.audit_log import log_logout
        await log_logout(db=db, user=current_user, request=request)
        # 注意：这里不commit，由get_db的finally块自动commit

        logger.info(f"User {current_user.username} logged out successfully")

        return {
            "message": "退出登录成功"
        }
    except Exception as e:
        # 日志记录失败不应该影响退出登录
        logger.warning(f"记录退出登录日志失败: {e}")
        return {
            "message": "退出登录成功"
        }
