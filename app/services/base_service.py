"""
服务基类
提供通用服务方法和工具函数
"""
from typing import Generic, TypeVar, Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from app.models.models import User, UserRole
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseService(Generic[T]):
    """服务基类，提供通用方法"""
    
    def __init__(self, db: AsyncSession, model: type[T]):
        self.db = db
        self.model = model
    
    async def get_by_id(self, id: int) -> Optional[T]:
        """根据ID获取实体"""
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[T]:
        """获取所有实体（支持过滤）"""
        query = select(self.model)
        
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    query = query.where(getattr(self.model, key) == value)
        
        result = await self.db.execute(
            query.offset(skip).limit(limit)
        )
        return result.scalars().all()
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """统计实体数量"""
        query = select(func.count(self.model.id))
        
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    query = query.where(getattr(self.model, key) == value)
        
        result = await self.db.execute(query)
        return result.scalar() or 0
    
    def check_permission(self, user: User, resource_user_id: Optional[int] = None) -> bool:
        """
        检查用户权限
        - 管理员有所有权限
        - 客户只能访问自己的资源
        
        Args:
            user: 当前用户
            resource_user_id: 资源所属用户ID（如果资源属于某个用户）
        
        Returns:
            bool: 是否有权限
        """
        if user.role == UserRole.ADMIN:
            return True
        
        if resource_user_id is not None:
            return user.id == resource_user_id
        
        return False
    
    def require_admin(self, user: User) -> None:
        """要求管理员权限，否则抛出异常"""
        if user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="此操作需要管理员权限"
            )

