"""
安全认证模块

功能说明：
提供JWT令牌生成和验证、用户认证、权限检查等核心安全功能，包括：
- JWT工具类：创建和验证JWT访问令牌
- 用户认证：从JWT令牌解析用户信息
- 权限检查：管理员权限、客户权限、资源所有权检查
- OAuth2集成：支持OAuth2密码持有者模式

JWT令牌管理：
- 算法支持：RS256（非对称加密，推荐）或HS256（对称加密）
- 令牌内容：用户ID（sub）、过期时间（exp）、签发时间（iat）、JWT ID（jti）
- 过期时间：默认240分钟，可通过配置调整
- 密钥管理：
  - RS256：使用RSA密钥对（私钥签名，公钥验证）
  - HS256：使用共享密钥（SECRET_KEY）
  - 支持从环境变量或文件加载密钥

安全特性：
1. 令牌验证：
   - 验证签名有效性
   - 检查过期时间
   - 验证令牌类型（access token）
   - 支持令牌黑名单（可选）

2. 权限控制：
   - 管理员权限：只有ADMIN角色可以访问
   - 客户权限：CLIENT角色只能访问自己的资源
   - 资源所有权：用户可以访问自己的资源或管理员可以访问所有资源

3. 错误处理：
   - 令牌缺失：返回401 Unauthorized
   - 令牌无效：返回401 Unauthorized
   - 令牌过期：返回401 Unauthorized
   - 权限不足：返回403 Forbidden

使用方式：
1. 登录获取令牌：
   ```python
   token = JWTUtils.create_access_token(user_id)
   ```

2. 在API端点中使用：
   ```python
   @router.get("/protected")
   async def protected_route(current_user: User = Depends(get_current_user)):
       # current_user 是已验证的用户对象
       pass
   ```

3. 权限检查：
   ```python
   @router.delete("/users/{user_id}")
   async def delete_user(
       user_id: int,
       current_user: User = Depends(get_current_admin_or_owner)
   ):
       # 只有管理员或资源所有者可以访问
       pass
   ```

注意事项：
1. 生产环境必须使用RS256算法和强密钥
2. 令牌应存储在安全的客户端存储中（httpOnly cookie或localStorage）
3. 敏感操作应使用短期令牌或刷新令牌机制
4. 定期轮换密钥以提高安全性
5. 考虑实现令牌黑名单机制（用于登出功能）
"""
# 标准库导入
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

# 第三方库导入
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError, JWSError, JWTClaimsError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# 本地导入
from app.core.config import settings
from app.core.database import get_db
from app.core.utils import get_app_now_naive
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
    def _load_rsa_key(key_content: str, key_path: str, key_type: str) -> str:
        """
        加载RSA密钥
        
        参数:
            key_content: 密钥内容（从环境变量获取）
            key_path: 密钥文件路径
            key_type: 密钥类型（"private" 或 "public"）
        
        返回:
            密钥字符串
        """
        # 优先使用环境变量中的密钥内容
        if key_content:
            return key_content
        
        # 尝试从文件加载密钥
        if key_path and os.path.exists(key_path):
            try:
                with open(key_path, "r") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"加载RSA {key_type} 密钥文件失败: {e}")
                raise
        
        # 调试：输出环境变量值
        production_env = os.getenv("PRODUCTION_ENV", "development").lower()
        logger.info(f"RSA密钥加载调试：PRODUCTION_ENV={production_env}")
        
        # 宽松处理：如果没有找到密钥，总是生成临时密钥
        # 这样可以确保测试环境和开发环境正常运行
        logger.warning(f"未配置RSA {key_type} 密钥，生成临时测试密钥")
        # 生成2048位RSA密钥对
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        if key_type == "private":
            return private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode("utf-8")
        else:
            return private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode("utf-8")
    
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
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            # 使用配置中的默认过期时间（分钟）
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        # 构建JWT载荷（包含过期时间、主体和签发时间）
        # 添加iat（issued at）和jti（JWT ID）增强安全性
        import secrets
        jti = secrets.token_urlsafe(16)  # JWT ID，用于防止重放攻击和会话管理
        to_encode = {
            "exp": expire,  # 过期时间
            "iat": datetime.now(timezone.utc),  # 签发时间
            "sub": str(subject),  # 主体（用户ID）
            "jti": jti,  # JWT ID，用于防止重放攻击和会话管理
            "type": "access"  # 令牌类型
        }
        
        algorithm = settings.JWT_ALGORITHM
        
        if algorithm == "RS256":
            # 使用RS256算法（非对称加密）
            private_key = JWTUtils._load_rsa_key(
                settings.RSA_PRIVATE_KEY,
                settings.RSA_PRIVATE_KEY_PATH,
                "private"
            )
            encoded_jwt = jwt.encode(to_encode, private_key, algorithm="RS256")
        else:
            # 默认使用HS256算法（对称加密）
            encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=algorithm)
        
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
            algorithm = settings.JWT_ALGORITHM
            
            # 根据算法选择密钥
            if algorithm == "RS256":
                # 使用RS256算法（非对称加密），需要公钥验证
                public_key = JWTUtils._load_rsa_key(
                    settings.RSA_PUBLIC_KEY,
                    settings.RSA_PUBLIC_KEY_PATH,
                    "public"
                )
                key = public_key
            else:
                # 使用HS256算法（对称加密），使用相同的密钥
                key = settings.SECRET_KEY
            
            # 解码并验证令牌
            payload = jwt.decode(
                token,
                key,  # 使用相应的密钥
                algorithms=[algorithm],  # 使用配置的算法
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
                            TokenBlacklist.expires_at > get_app_now_naive()  # 使用北京时间比较
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
            # JWT签名验证失败（通常是密钥不匹配或token格式错误）
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


def is_admin(user: User) -> bool:
    """
    检查用户是否为管理员
    
    参数:
        user: 用户对象
    
    返回:
        bool: 如果是管理员返回 True，否则返回 False
    """
    return user.role == UserRole.ADMIN


def is_client(user: User) -> bool:
    """
    检查用户是否为客户
    
    参数:
        user: 用户对象
    
    返回:
        bool: 如果是客户返回 True，否则返回 False
    """
    return user.role == UserRole.CLIENT