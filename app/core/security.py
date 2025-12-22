"""
安全认证模块
提供JWT令牌生成和验证、用户认证、权限检查等功能
包括：
- JWT工具类（创建和验证令牌）
- 当前用户获取（从JWT令牌解析）
- 管理员权限检查
- 客户权限检查
- 管理员或自己的权限检查
"""
# 标准库导入
import logging
from datetime import datetime, timedelta
from typing import Any

# 第三方库导入
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError, JWSError, JWTClaimsError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# 本地导入
from app.core.config import settings
from app.core.database import get_db
from app.models.models import User, UserRole

# 获取日志记录器
logger = logging.getLogger(__name__)

# ====== OAuth2配置 ======
# 配置OAuth2密码持有者模式，指定令牌获取端点
# auto_error=False 允许我们在 header 缺失时，在程序逻辑中从 cookie 提取 token
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False
)


# ====== JWT工具类 ======
class JWTUtils:
    """
    JWT工具类
    提供令牌的创建和验证功能
    """

    @staticmethod
    def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
        """
        生成JWT访问令牌
        
        参数:
            subject: 令牌主体（通常是用户ID）
            expires_delta: 可选的过期时间增量，如果不提供则使用配置的默认值
        
        返回:
            JWT令牌字符串
        """
        # 计算过期时间（使用UTC时间，避免时区问题）
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            # 使用配置中的默认过期时间（分钟）
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        # 构建JWT载荷（包含过期时间、主体和签发时间）
        # 添加iat（issued at）和jti（JWT ID）增强安全性
        import secrets
        jti = secrets.token_urlsafe(16)  # JWT ID，用于防止重放攻击和会话管理
        to_encode = {
            "exp": expire,  # 过期时间
            "iat": datetime.utcnow(),  # 签发时间
            "sub": str(subject),  # 主体（用户ID）
            "jti": jti,  # JWT ID，用于防止重放攻击和会话管理
            "type": "access"  # 令牌类型
        }
        # 使用HS256算法和密钥编码令牌
        # 生产环境建议使用RS256（非对称加密），但HS256（对称加密）更简单且足够安全
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
        return encoded_jwt

    @staticmethod
    async def verify_token(token: str, db: AsyncSession | None = None) -> dict:
        """
        验证JWT令牌并返回载荷
        同时检查token是否在黑名单中
        
        参数:
            token: JWT令牌字符串
            db: 数据库会话（可选，用于检查黑名单）
        
        返回:
            解码后的令牌载荷（字典）
        
        异常:
            HTTPException: 如果令牌无效、过期或在黑名单中
        """
        try:
            # 解码并验证令牌
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,  # 使用相同的密钥
                algorithms=["HS256"],  # 使用HS256算法
                options={"verify_aud": False}  # 不验证受众（audience）
            )
            
            # 检查token是否在黑名单中（如果提供了数据库会话）
            if db:
                jti = payload.get("jti")
                if jti:
                    from app.models.session import TokenBlacklist
                    from sqlalchemy.future import select
                    result = await db.execute(
                        select(TokenBlacklist).where(
                            TokenBlacklist.token_jti == jti,
                            TokenBlacklist.expires_at > datetime.utcnow()
                        )
                    )
                    blacklisted = result.scalars().first()
                    if blacklisted:
                        logger.warning(f"JWT令牌已被撤销: jti={jti[:8]}...")
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="登录已失效，请重新登录",
                            headers={"WWW-Authenticate": "Bearer"},
                        )
            
            return payload
        except HTTPException:
            # 重新抛出HTTP异常
            raise
        except ExpiredSignatureError:
            # 令牌已过期
            logger.warning(f"JWT令牌已过期")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="登录已过期，请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except JWTClaimsError as e:
            # JWT声明错误
            logger.error(f"JWT声明错误: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的身份验证令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except JWSError as e:
            # JWT签名验证失败（通常是SECRET_KEY不匹配或token格式错误）
            # 只在debug模式下记录详细错误，避免日志过多
            logger.debug(f"JWT签名验证失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="登录已过期，请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except JWTError as e:
            # 其他JWT验证错误（如token格式错误、签名不匹配等）
            # 只在debug模式下记录详细错误，避免日志过多
            logger.debug(f"JWT验证错误: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的身份验证令牌，请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except ValidationError:
            # 载荷验证失败
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌验证失败，请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            )


# ====== 获取当前用户依赖 ======
async def get_current_user(
        request: Request,
        db: AsyncSession = Depends(get_db),
        token: str = Depends(oauth2_scheme)
) -> User:
    """
    从JWT令牌中获取当前用户
    
    支持两种方式：
    1. Authorization: Bearer <token> 请求头 (传统前端方式)
    2. HttpOnly Cookie: access_token (安全增强方式)
    
    参数:
        request: FastAPI 请求对象
        db: 数据库会话
        token: JWT令牌（从请求头自动提取）
    """
    # ====== 令牌提取优先级 ======
    # 如果请求头中没有 token (oauth2_scheme 返回 None 或解析失败)
    # 则尝试从 Cookie 中获取
    if not token:
        token = request.cookies.get("access_token")
        
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ====== 验证令牌 ======
    # 验证JWT令牌并获取载荷（同时检查黑名单）
    payload = await JWTUtils.verify_token(token, db=db)

    # ====== 提取用户ID ======
    # 从载荷中获取用户ID（subject）
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法从令牌中获取用户ID",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ====== 查询用户 ======
    # 从数据库查询用户信息
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalars().first()

    if user is None:
        # 用户不存在（可能已被删除）
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ====== 用户状态检查 ======
    # 检查用户是否被禁用
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户登录是否受限
    if user.login_restricted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=user.login_message or "登录已被限制",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# ====== 管理员权限依赖 ======
async def require_admin(
        current_user: User = Depends(get_current_user)
) -> User:
    """
    检查当前用户是否为管理员
    
    这是一个FastAPI依赖项，用于保护需要管理员权限的端点
    
    参数:
        current_user: 当前用户（从get_current_user获取）
    
    返回:
        当前用户对象（如果是管理员）
    
    异常:
        HTTPException: 如果用户不是管理员
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


# ====== 客户权限依赖 ======
async def require_client(
        current_user: User = Depends(get_current_user)
) -> User:
    """
    检查当前用户是否为客户
    
    这是一个FastAPI依赖项，用于保护需要客户权限的端点
    
    参数:
        current_user: 当前用户（从get_current_user获取）
    
    返回:
        当前用户对象（如果是客户）
    
    异常:
        HTTPException: 如果用户不是客户
    """
    if current_user.role != UserRole.CLIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要客户权限",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


# 管理员或客户自身权限依赖
async def require_admin_or_self(
        client_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
) -> User:
    if current_user.role == UserRole.ADMIN:
        return current_user

    # 检查当前客户是否有权限访问自己的数据
    # 注意：Client 需要在函数内导入以避免循环导入
    from app.models.models import Client
    result = await db.execute(select(Client).where(Client.user_id == current_user.id, Client.id == client_id))
    client = result.scalars().first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有权限访问此客户数据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return current_user
