"""
用户权限 Redis 缓存模块。

职责：缓存用户角色、client_id、api_enabled 等鉴权字段，减少每次请求的 User 表查询。

在系统中的位置：``app.core.permission_cache``，由 ``security.get_current_user`` 链路调用。
"""
import logging
import json
from typing import Optional, Dict, Any
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.redis_client import get_redis_client
from app.models.models import User, UserRole
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

# 缓存键前缀
PERMISSION_CACHE_PREFIX = "permission:"
# 缓存过期时间（秒）- 5分钟
PERMISSION_CACHE_TTL = 300


async def get_user_permissions(user_id: int, db: AsyncSession) -> Dict[str, Any]:
    """
    获取用户权限信息（带缓存）
    
    权限信息包括：
    - role: 用户角色（admin/client）
    - is_active: 是否激活
    - login_restricted: 是否限制登录
    - client_id: 客户ID（如果是客户角色）
    - api_enabled: API访问开关（如果是客户角色）
    
    Args:
        user_id: 用户ID
        db: 数据库会话
    
    Returns:
        权限信息字典
    """
    redis = await get_redis_client()
    cache_key = f"{PERMISSION_CACHE_PREFIX}{user_id}"
    
    # 尝试从缓存获取
    if redis:
        try:
            cached_data = await redis.get(cache_key)
            if cached_data:
                permissions = json.loads(cached_data)
                logger.debug(f"从缓存获取用户权限: user_id={user_id}")
                return permissions
        except Exception as e:
            logger.warning(f"从缓存获取用户权限失败: {e}")
    
    # 从数据库查询（如果是客户角色，同时加载客户信息）
    result = await db.execute(
        select(User)
        .options(selectinload(User.clients))
        .where(User.id == user_id)
    )
    user = result.scalars().first()
    
    if not user:
        return {
            "role": None,
            "is_active": False,
            "login_restricted": False,
            "client_id": None,
            "api_enabled": False
        }
    
    # 构建权限信息
    permissions = {
        "role": user.role.value if user.role else None,
        "is_active": user.is_active,
        "login_restricted": user.login_restricted,
        "client_id": None,
        "api_enabled": False
    }
    
    # 如果是客户角色，获取客户信息
    if user.role == UserRole.CLIENT and user.clients:
        client = user.clients[0]
        if client:
            permissions["client_id"] = client.id
            permissions["api_enabled"] = client.api_enabled
    
    # 写入缓存
    if redis:
        try:
            await redis.setex(
                cache_key,
                PERMISSION_CACHE_TTL,
                json.dumps(permissions)
            )
            logger.debug(f"用户权限已缓存: user_id={user_id}")
        except Exception as e:
            logger.warning(f"缓存用户权限失败: {e}")
    
    return permissions


async def invalidate_user_permission_cache(user_id: int) -> None:
    """
    清除用户权限缓存
    
    Args:
        user_id: 用户ID
    """
    redis = await get_redis_client()
    if redis:
        try:
            cache_key = f"{PERMISSION_CACHE_PREFIX}{user_id}"
            await redis.delete(cache_key)
            logger.debug(f"已清除用户权限缓存: user_id={user_id}")
        except Exception as e:
            logger.warning(f"清除用户权限缓存失败: {e}")


async def is_admin_cached(user_id: int, db: AsyncSession) -> bool:
    """
    检查用户是否为管理员（带缓存）
    
    Args:
        user_id: 用户ID
        db: 数据库会话
    
    Returns:
        是否为管理员
    """
    permissions = await get_user_permissions(user_id, db)
    return permissions.get("role") == "admin"


async def can_access_resource_cached(
    user_id: int,
    resource_user_id: Optional[int],
    db: AsyncSession
) -> bool:
    """
    检查用户是否可以访问资源（带缓存）
    
    规则：
    - 管理员可以访问所有资源
    - 客户只能访问自己的资源
    
    Args:
        user_id: 用户ID
        resource_user_id: 资源所属用户ID（如果资源属于某个用户）
        db: 数据库会话
    
    Returns:
        是否可以访问
    """
    permissions = await get_user_permissions(user_id, db)
    
    # 管理员可以访问所有资源
    if permissions.get("role") == "admin":
        return True
    
    # 客户只能访问自己的资源
    if resource_user_id is not None:
        return user_id == resource_user_id
    
    return False
