"""
服务基类
提供通用服务方法和工具函数

职责：
- 业务逻辑封装
- 权限检查
- 数据验证
- 不直接操作数据库（通过仓储层）
"""
from typing import Generic, TypeVar, Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User, UserRole
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.repositories.base_repository import BaseRepository
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseService(Generic[T]):
    """
    服务基类，提供通用方法
    
    设计原则：
    - 服务层包含业务逻辑
    - 数据访问通过仓储层
    - 权限检查在服务层完成
    """
    
    def __init__(self, db: AsyncSession, model: type[T], repository: Optional[BaseRepository[T]] = None):
        """
        初始化服务
        
        Args:
            db: 数据库会话
            model: 模型类
            repository: 仓储实例（如果为None，会自动创建）
        """
        self.db = db
        self.model = model
        self._repository = repository or BaseRepository(db, model)
    
    @property
    def repository(self) -> BaseRepository[T]:
        """获取仓储实例"""
        return self._repository
    
    async def get_by_id(
        self,
        id: int,
        load_relations: Optional[List[str]] = None
    ) -> Optional[T]:
        """
        根据ID获取实体（通过仓储层）
        
        Args:
            id: 实体ID
            load_relations: 要预加载的关联关系列表
        
        Returns:
            实体对象或None
        """
        return await self.repository.get_by_id(id, load_relations=load_relations)
    
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        desc_order: bool = True,
        load_relations: Optional[List[str]] = None
    ) -> List[T]:
        """
        获取所有实体（通过仓储层）
        
        Args:
            skip: 跳过记录数
            limit: 限制记录数
            filters: 过滤条件
            order_by: 排序字段
            desc_order: 是否降序
            load_relations: 要预加载的关联关系列表
        
        Returns:
            实体列表
        """
        return await self.repository.get_all(
            skip=skip,
            limit=limit,
            filters=filters,
            order_by=order_by,
            desc_order=desc_order,
            load_relations=load_relations
        )
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        统计实体数量（通过仓储层）
        
        Args:
            filters: 过滤条件
        
        Returns:
            记录总数
        """
        return await self.repository.count(filters=filters)
    
    async def paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        search_fields: Optional[List[str]] = None,
        search_keyword: Optional[str] = None,
        order_by: Optional[str] = None,
        desc_order: bool = True,
        load_relations: Optional[List[str]] = None
    ) -> Tuple[List[T], int]:
        """
        分页查询（通过仓储层）
        
        Args:
            page: 页码
            page_size: 每页数量
            filters: 过滤条件
            search_fields: 搜索字段列表
            search_keyword: 搜索关键词
            order_by: 排序字段
            desc_order: 是否降序
            load_relations: 要预加载的关联关系列表
        
        Returns:
            (实体列表, 总数)
        """
        return await self.repository.paginated(
            page=page,
            page_size=page_size,
            filters=filters,
            search_fields=search_fields,
            search_keyword=search_keyword,
            order_by=order_by,
            desc_order=desc_order,
            load_relations=load_relations
        )
    
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
        """
        要求管理员权限，否则抛出异常
        
        Args:
            user: 当前用户
        
        Raises:
            APIException: 如果不是管理员
        """
        if user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="此操作需要管理员权限"
            )
    
    def require_owner_or_admin(
        self,
        user: User,
        resource_user_id: Optional[int]
    ) -> None:
        """
        要求资源所有者或管理员权限
        
        Args:
            user: 当前用户
            resource_user_id: 资源所属用户ID
        
        Raises:
            APIException: 如果没有权限
        """
        if not self.check_permission(user, resource_user_id):
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="无权访问该资源"
            )

