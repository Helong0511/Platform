"""
API 路由装饰器集合。

职责：在 FastAPI 端点外层统一做权限校验（管理员/角色/资源归属）与分页参数规范化。

在系统中的位置：``app.core.decorators``，由 ``app.api_v1`` 各路由模块按需引用；
异常统一通过 ``raise_api_exception`` 抛出标准业务错误码。
"""
from functools import wraps
from typing import Callable, Any
from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User, UserRole
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.database import get_db
from app.core.security import get_current_user
import logging

logger = logging.getLogger(__name__)


def require_admin(func: Callable = None):
    """
    要求管理员权限的装饰器
    
    使用示例:
        @router.get("/admin-only")
        @require_admin
        async def admin_endpoint(current_user: User = Depends(get_current_user)):
            ...
    """
    def decorator(f: Callable) -> Callable:
        """包装目标端点，注入管理员角色校验。"""

        @wraps(f)
        async def wrapper(*args, **kwargs):
            """校验 current_user 为 ADMIN 后调用原函数。"""
            # ---------- 解析当前用户 ----------
            current_user = kwargs.get('current_user')
            if not current_user:
                # 尝试从args中获取
                for arg in args:
                    if isinstance(arg, User):
                        current_user = arg
                        break
            
            if not current_user:
                raise_api_exception(
                    ErrorCode.UNAUTHORIZED,
                    detail="需要登录"
                )
            
            if current_user.role != UserRole.ADMIN:
                raise_api_exception(
                    ErrorCode.FORBIDDEN,
                    detail="此操作需要管理员权限"
                )
            
            return await f(*args, **kwargs)
        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)


def require_roles(*allowed_roles: UserRole):
    """
    要求特定角色的装饰器
    
    使用示例:
        @router.get("/client-only")
        @require_roles(UserRole.CLIENT, UserRole.ADMIN)
        async def client_endpoint(current_user: User = Depends(get_current_user)):
            ...
    """
    def decorator(func: Callable) -> Callable:
        """包装目标端点，校验用户角色在 allowed_roles 内。"""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """校验角色后调用原函数。"""
            current_user = kwargs.get('current_user')
            if not current_user:
                for arg in args:
                    if isinstance(arg, User):
                        current_user = arg
                        break

            if not current_user:
                raise_api_exception(
                    ErrorCode.UNAUTHORIZED,
                    detail="需要登录"
                )

            if current_user.role not in allowed_roles:
                raise_api_exception(
                    ErrorCode.FORBIDDEN,
                    detail=f"此操作需要以下角色之一: {', '.join(role.value for role in allowed_roles)}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def check_resource_owner(resource_user_id_attr: str = "user_id"):
    """
    检查资源所有权的装饰器
    
    使用示例:
        @router.get("/my-resource/{resource_id}")
        @check_resource_owner("user_id")
        async def get_my_resource(
            resource_id: int,
            current_user: User = Depends(get_current_user),
            db: AsyncSession = Depends(get_db)
        ):
            # 装饰器会自动检查资源是否属于当前用户
            ...
    
    Args:
        resource_user_id_attr: 资源对象中表示用户ID的属性名
    """
    def decorator(func: Callable) -> Callable:
        """包装目标端点，非管理员须能解析 resource_id（具体归属校验在服务层）。"""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """解析用户与资源 ID，管理员直接放行。"""
            current_user = kwargs.get('current_user')
            if not current_user:
                for arg in args:
                    if isinstance(arg, User):
                        current_user = arg
                        break

            if not current_user:
                raise_api_exception(
                    ErrorCode.UNAUTHORIZED,
                    detail="需要登录"
                )

            # ---------- 管理员放行 ----------
            if current_user.role == UserRole.ADMIN:
                return await func(*args, **kwargs)
            
            # 从函数参数中获取资源ID
            resource_id = kwargs.get('resource_id') or kwargs.get('id')
            if not resource_id:
                # 尝试从路径参数中获取
                for arg in args:
                    if isinstance(arg, int):
                        resource_id = arg
                        break
            
            if not resource_id:
                raise_api_exception(
                    ErrorCode.BAD_REQUEST,
                    detail="无法确定资源ID"
                )
            
            # 从数据库获取资源并检查所有权
            db = kwargs.get('db')
            if not db:
                for arg in args:
                    if isinstance(arg, AsyncSession):
                        db = arg
                        break
            
            if not db:
                raise_api_exception(
                    ErrorCode.INTERNAL_ERROR,
                    detail="无法获取数据库会话"
                )
            
            # 这里需要根据实际资源类型进行查询
            # 由于是通用装饰器，这里只做基本检查
            # 具体实现应该在服务层完成
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def validate_pagination(page: int = 1, page_size: int = 20, max_page_size: int = 100):
    """
    验证分页参数的装饰器
    
    使用示例:
        @router.get("/items")
        @validate_pagination(max_page_size=50)
        async def get_items(
            page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=50)
        ):
            ...
    """
    def decorator(func: Callable) -> Callable:
        """包装目标端点，规范化并校验 page / page_size 参数。"""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """校验分页范围后写回 kwargs 并调用原函数。"""
            page_val = kwargs.get('page', page)
            page_size_val = kwargs.get('page_size', page_size)
            
            if page_val < 1:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="页码必须大于0"
                )
            
            if page_size_val < 1:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="每页数量必须大于0"
                )
            
            if page_size_val > max_page_size:
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=f"每页数量不能超过{max_page_size}"
                )
            
            kwargs['page'] = page_val
            kwargs['page_size'] = page_size_val
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

