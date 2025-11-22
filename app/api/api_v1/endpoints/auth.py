"""
用户认证API端点
提供用户登录和身份验证功能，包括：
- 用户登录（验证凭据并生成JWT令牌）
- 验证用户状态（激活状态、登录限制）
- 客户IP白名单验证
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
from app.models.models import Client, User, UserRole
from app.schemas.auth import LoginResponse

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)


@router.post("/login", response_model=LoginResponse, summary="用户登录")
async def login(
        request: Request,
        db: AsyncSession = Depends(get_db),
        form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    用户登录接口，验证凭据并返回JWT令牌
    - 验证用户名和密码
    - 生成访问令牌
    - 为管理员返回未读通知
    - 客户IP白名单验证（127.0.0.1始终允许）
    """
    # ====== 获取客户端IP ======
    from app.core.utils import get_client_ip
    client_ip = get_client_ip(request)

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
    try:
        from jose import jwt
        payload = jwt.decode(
            access_token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_exp": False}  # 不验证过期时间，只获取jti
        )
        token_jti = payload.get("jti")
        
        if token_jti:
            # 记录会话到数据库
            from app.models.session import UserSession
            from app.core.utils import get_client_ip, get_device_type
            
            expires_at = datetime.now(timezone.utc) + access_token_expires
            device_type_str = get_device_type(request)
            user_agent = request.headers.get("User-Agent", "")[:500]
            
            session = UserSession(
                user_id=user.id,
                token_jti=token_jti,
                ip_address=client_ip,
                user_agent=user_agent,
                device_info=device_type_str,
                is_active=True,
                last_activity=datetime.now(timezone.utc),
                expires_at=expires_at
            )
            db.add(session)
            # 不在这里commit，由get_db的finally块自动commit
    except Exception as e:
        # 会话记录失败不应该影响登录
        logger.warning(f"记录会话信息失败: {e}")

    logger.info(f"User {user.username} logged in successfully")

    # 先返回响应，不阻塞登录流程
    # 如果是客户角色，获取客户的api_enabled信息
    api_enabled = False
    if user.role == UserRole.CLIENT and user.clients:
        # 客户用户：获取第一个客户的api_enabled状态
        client = user.clients[0]
        api_enabled = client.api_enabled if client else False
    
    response_data = {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.value,
            "api_enabled": api_enabled  # 客户API访问开关状态
        }
    }

    # 异步记录登录日志（不阻塞响应）
    # 使用后台任务记录日志，避免阻塞登录响应
    try:
        from app.core.audit_log import log_login
        # 在后台记录日志，不等待完成
        await log_login(db=db, user=user, request=request, success=True)
        # 注意：这里不commit，由get_db的finally块自动commit
    except Exception as e:
        # 日志记录失败不应该影响登录
        logger.warning(f"记录登录日志失败: {e}")

    return response_data


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
