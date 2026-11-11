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
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

# 第三方库导入
from fastapi import Depends, HTTPException, Request, status

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from fastapi.security import OAuth2PasswordBearer
from app.core.jwt_codec import (
    ExpiredSignatureError,
    JWTClaimsError,
    JWTError,
    JWSError,
    decode as jwt_decode,
    encode as jwt_encode,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# 本地导入
from app.core.config import settings
from app.core.database import get_db
from app.core.utils import get_app_now_naive
from app.models.models import User, UserRole
from app.models.session import TokenBlacklist

# 获取日志记录器
logger = logging.getLogger(__name__)

# ====== OAuth2配置 ======
# 配置OAuth2密码持有者模式，指定令牌获取端点
# auto_error=False 允许我们在 header 缺失时，在程序逻辑中从 cookie 提取 token
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False
)

# 开发环境无 RSA 文件时，进程内复用同一对临时密钥（避免每次加载生成新密钥导致验签失败）
_ephemeral_rsa_private_pem: str | None = None
_ephemeral_rsa_public_pem: str | None = None


def _generate_ephemeral_rsa_pair() -> tuple[str, str]:
    """生成并缓存进程级临时 RSA 密钥对（仅当未配置密钥文件时使用）。"""
    global _ephemeral_rsa_private_pem, _ephemeral_rsa_public_pem
    if _ephemeral_rsa_private_pem and _ephemeral_rsa_public_pem:
        return _ephemeral_rsa_private_pem, _ephemeral_rsa_public_pem

    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    _ephemeral_rsa_private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    _ephemeral_rsa_public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return _ephemeral_rsa_private_pem, _ephemeral_rsa_public_pem


def _resolve_rsa_key_path(key_path: str) -> str:
    """将 Linux 部署路径映射到本地 keys/ 目录（Windows 开发用）。"""
    if key_path and os.path.exists(key_path):
        return key_path
    if not key_path:
        return key_path
    filename = os.path.basename(key_path.replace("\\", "/"))
    if not filename:
        return key_path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    local_path = os.path.join(project_root, "keys", filename)
    return local_path if os.path.exists(local_path) else key_path


def _raise_auth(
        detail: str,
        *,
        error_code: int = ErrorCode.UNAUTHORIZED,
        http_status: int = status.HTTP_401_UNAUTHORIZED,
) -> None:
    """认证/鉴权失败：标准 JSON 响应体 + 保留真实 HTTP 状态码。"""
    raise_api_exception(error_code, detail=detail, status_code=http_status)


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
        
        # 尝试从文件加载密钥（含项目 keys/ 目录回退）
        resolved_path = _resolve_rsa_key_path(key_path)
        if resolved_path and os.path.exists(resolved_path):
            try:
                with open(resolved_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"加载RSA {key_type} 密钥文件失败: {e}")
                raise
        
        # 调试：输出环境变量值
        from app.core.config import detect_production_env
        production_env = detect_production_env()
        logger.info(f"RSA密钥加载调试：PRODUCTION_ENV={production_env}")
        
        # 无密钥文件：使用进程内固定的临时密钥对
        logger.warning(f"未配置RSA {key_type} 密钥，使用进程内临时测试密钥对")
        private_pem, public_pem = _generate_ephemeral_rsa_pair()
        return private_pem if key_type == "private" else public_pem
    
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
            encoded_jwt = jwt_encode(to_encode, private_key, algorithm="RS256")
        else:
            # 默认使用HS256算法（对称加密）
            encoded_jwt = jwt_encode(to_encode, settings.SECRET_KEY, algorithm=algorithm)
        
        return encoded_jwt

    @staticmethod
    def create_refresh_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
        """
        生成JWT刷新令牌
        
        刷新令牌的过期时间通常比访问令牌长（如7天或30天）
        
        参数:
            subject: 令牌主体（通常是用户ID）
            expires_delta: 可选的过期时间增量，默认7天
        
        返回:
            JWT刷新令牌字符串
        """
        # 刷新令牌默认过期时间为7天
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )

        # 构建JWT载荷
        jti = secrets.token_urlsafe(16)
        to_encode = {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "sub": str(subject),
            "jti": jti,
            "type": "refresh"  # 刷新令牌类型
        }
        
        algorithm = settings.JWT_ALGORITHM
        
        if algorithm == "RS256":
            private_key = JWTUtils._load_rsa_key(
                settings.RSA_PRIVATE_KEY,
                settings.RSA_PRIVATE_KEY_PATH,
                "private"
            )
            encoded_jwt = jwt_encode(to_encode, private_key, algorithm="RS256")
        else:
            encoded_jwt = jwt_encode(to_encode, settings.SECRET_KEY, algorithm=algorithm)
        
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
            payload = jwt_decode(
                token,
                key,  # 使用相应的密钥
                algorithms=[algorithm],  # 使用配置的算法
                options={"verify_aud": False}  # 不验证受众（audience）
            )
            
            # 检查token是否在黑名单中（Redis 优先，再查 MySQL）
            jti = payload.get("jti")
            if jti:
                try:
                    from app.core.token_blacklist_redis import is_jti_redis_blacklisted

                    if await is_jti_redis_blacklisted(str(jti)):
                        logger.warning("JWT令牌已被撤销(Redis): jti=%s...", str(jti)[:8])
                        _raise_auth(
                            "登录已失效，请重新登录",
                            error_code=ErrorCode.TOKEN_INVALID,
                        )
                except HTTPException:
                    # _raise_auth 抛出的 HTTPException 必须向上传播，不能被吞
                    raise
                except Exception as redis_exc:
                    logger.debug("Redis JWT 黑名单查询跳过: %s", redis_exc)

            if db and jti:
                result = await db.execute(
                    select(TokenBlacklist).where(
                        TokenBlacklist.token_jti == jti,
                        TokenBlacklist.expires_at > get_app_now_naive()  # 使用北京时间比较
                    )
                )
                blacklisted = result.scalars().first()
                if blacklisted:
                    logger.warning(f"JWT令牌已被撤销: jti={str(jti)[:8]}...")
                    # 回填 Redis，加速后续拦截
                    try:
                        from app.core.token_blacklist_redis import add_jti_to_redis_blacklist

                        await add_jti_to_redis_blacklist(
                            str(jti), blacklisted.expires_at, reason=blacklisted.reason or ""
                        )
                    except Exception:
                        pass
                    _raise_auth(
                        "登录已失效，请重新登录",
                        error_code=ErrorCode.TOKEN_INVALID,
                    )
            
            return payload
        except HTTPException:
            # 重新抛出HTTP异常
            raise
        except ExpiredSignatureError:
            # 令牌已过期
            logger.warning(f"JWT令牌已过期")
            _raise_auth(
                "登录已过期，请重新登录",
                error_code=ErrorCode.TOKEN_EXPIRED,
            )
        except JWTClaimsError as e:
            # JWT声明错误
            logger.error(f"JWT声明错误: {str(e)}")
            _raise_auth(
                "无效的身份验证令牌",
                error_code=ErrorCode.TOKEN_INVALID,
            )
        except JWSError as e:
            # JWT签名验证失败（通常是密钥不匹配或token格式错误）
            # 只在debug模式下记录详细错误，避免日志过多
            logger.debug(f"JWT签名验证失败: {str(e)}")
            _raise_auth(
                "登录已过期，请重新登录",
                error_code=ErrorCode.TOKEN_EXPIRED,
            )
        except JWTError as e:
            # 其他JWT验证错误（如token格式错误、签名不匹配等）
            # 只在debug模式下记录详细错误，避免日志过多
            logger.debug(f"JWT验证错误: {str(e)}")
            _raise_auth(
                "无效的身份验证令牌，请重新登录",
                error_code=ErrorCode.TOKEN_INVALID,
            )
        except ValidationError:
            # 载荷验证失败
            _raise_auth(
                "令牌验证失败，请重新登录",
                error_code=ErrorCode.TOKEN_INVALID,
            )


def extract_access_token_from_request(request: Request) -> str | None:
    """从 Authorization 头或 HttpOnly Cookie 提取访问令牌。"""
    authorization = request.headers.get("Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    cookie_token = request.cookies.get("access_token")
    if cookie_token and cookie_token.strip():
        return cookie_token.strip()
    return None


async def is_authenticated_request(request: Request) -> bool:
    """
    判断请求是否携带有效的访问令牌（管理员、客户登录后均视为已认证）。

    用于限流中间件：已认证请求计入独立高配额桶（auth-api），未登录按 IP/接口类别限流。
    不查黑名单（db=None），业务接口仍由 get_current_user 完整校验。
    """
    token = extract_access_token_from_request(request)
    if not token:
        return False
    try:
        payload = await JWTUtils.verify_token(token, db=None)
    except HTTPException:
        return False
    if payload.get("type") != "access":
        return False
    return bool(payload.get("sub"))


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
    if not token:
        token = extract_access_token_from_request(request)

    if not token:
        _raise_auth("未登录或令牌缺失", error_code=ErrorCode.UNAUTHORIZED)

    # ====== 验证令牌 ======
    # 验证JWT令牌并获取载荷（同时检查黑名单）
    payload = await JWTUtils.verify_token(token, db=db)

    # 仅允许 access；拒绝 refresh 冒充访问令牌
    if payload.get("type") != "access":
        _raise_auth(
            "无效的访问令牌类型",
            error_code=ErrorCode.TOKEN_INVALID,
        )

    # ====== 提取用户ID ======
    # 从载荷中获取用户ID（subject）
    user_id: str = payload.get("sub")
    if user_id is None:
        _raise_auth(
            "无法从令牌中获取用户ID",
            error_code=ErrorCode.TOKEN_INVALID,
        )

    # 每次认证都读取当前用户行：角色、禁用状态和登录限制必须反映数据库最新值。
    # 原权限缓存路径仍会再次查询 User 表，既未省去 DB 查询，又可能因缓存过期延迟账号状态变更。
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalars().first()

    if user is None:
        _raise_auth(
            "用户不存在",
            error_code=ErrorCode.USER_NOT_FOUND,
            http_status=status.HTTP_404_NOT_FOUND,
        )

    if not user.is_active:
        _raise_auth(
            "用户已被禁用",
            error_code=ErrorCode.USER_DISABLED,
            http_status=status.HTTP_403_FORBIDDEN,
        )
    if user.login_restricted:
        _raise_auth(
            user.login_message or "登录已被限制",
            error_code=ErrorCode.FORBIDDEN,
            http_status=status.HTTP_403_FORBIDDEN,
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
        _raise_auth(
            "需要管理员权限",
            error_code=ErrorCode.FORBIDDEN,
            http_status=status.HTTP_403_FORBIDDEN,
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
        _raise_auth(
            "需要客户权限",
            error_code=ErrorCode.FORBIDDEN,
            http_status=status.HTTP_403_FORBIDDEN,
        )
    return current_user


# 管理员或客户自身权限依赖
async def require_admin_or_self(
        client_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
) -> User:
    """
    要求当前用户为管理员，或为客户且仅能访问自身 client_id 对应的数据。

    Args:
        client_id: 目标下游客户 ID
        current_user: 当前登录用户（依赖注入）
        db: 数据库会话（依赖注入）

    Returns:
        通过校验的 User 对象

    Raises:
        HTTPException: 非管理员且无权访问该客户时返回 403
    """
    if current_user.role == UserRole.ADMIN:
        return current_user

    # 检查当前客户是否有权限访问自己的数据
    # 注意：Client 需要在函数内导入以避免循环导入
    from app.models.models import Client
    result = await db.execute(select(Client).where(Client.user_id == current_user.id, Client.id == client_id))
    client = result.scalars().first()

    if not client:
        _raise_auth(
            "没有权限访问此客户数据",
            error_code=ErrorCode.CLIENT_NO_PERMISSION,
            http_status=status.HTTP_403_FORBIDDEN,
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


async def require_publisher_or_admin(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
) -> User:
    """
    要求管理员，或已关联下游渠道的客户用户。

    用于 Offer 列表、转化总览等 CPL 客户可见接口，与前端 requiresPublisher 路由守卫一致。
    """
    if current_user.role == UserRole.ADMIN:
        return current_user
    if current_user.role != UserRole.CLIENT:
        _raise_auth(
            "需要管理员或渠道客户权限",
            error_code=ErrorCode.FORBIDDEN,
            http_status=status.HTTP_403_FORBIDDEN,
        )
    from app.models.models import Client
    from app.services.user_service import UserService

    client_row = await db.execute(select(Client).where(Client.user_id == current_user.id))
    client = client_row.scalars().first()
    if not client:
        _raise_auth(
            "客户信息不存在",
            error_code=ErrorCode.CLIENT_NOT_FOUND,
            http_status=status.HTTP_403_FORBIDDEN,
        )
    if not await UserService(db).check_client_has_publisher(client.id):
        _raise_auth(
            "需要关联渠道权限",
            error_code=ErrorCode.FORBIDDEN,
            http_status=status.HTTP_403_FORBIDDEN,
        )
    return current_user