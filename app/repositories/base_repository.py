"""
仓储基类
提供通用的数据访问方法
使用查询构建器优化查询性能
"""
from typing import Generic, TypeVar, Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, desc, asc
from sqlalchemy.orm import joinedload, selectinload

from app.core.query_builder import QueryBuilder, build_query

T = TypeVar('T')


class BaseRepository(Generic[T]):
    """
    仓储基类，提供通用CRUD操作
    
    职责：
    - 数据访问（数据库操作）
    - 查询构建
    - 不包含业务逻辑
    """
    
    def __init__(self, db: AsyncSession, model: type[T]):
        """
        初始化仓储
        
        Args:
            db: 数据库会话
            model: 模型类
        """
        self.db = db
        self.model = model
    
    def query_builder(self) -> QueryBuilder:
        """
        获取查询构建器
        
        Returns:
            QueryBuilder实例
        """
        return QueryBuilder(self.db, self.model)
    
    async def get_by_id(
        self,
        id: int,
        load_relations: Optional[List[str]] = None
    ) -> Optional[T]:
        """
        根据ID获取实体
        
        Args:
            id: 实体ID
            load_relations: 要预加载的关联关系列表
        
        Returns:
            实体对象或None
        """
        builder = self.query_builder().base()
        
        if load_relations:
            builder.load_relations(*load_relations)
        
        builder._query = builder._query.where(self.model.id == id)
        return await builder.first()
    
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
        获取所有实体（支持过滤和排序）
        
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
        builder = build_query(
            db=self.db,
            model=self.model,
            filters=filters,
            order_by_field=order_by,
            desc_order=desc_order
        )
        
        if load_relations:
            builder.load_relations(*load_relations)
        
        builder._query = builder._query.offset(skip).limit(limit)
        return await builder.all()
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        统计实体数量
        
        Args:
            filters: 过滤条件
        
        Returns:
            记录总数
        """
        builder = self.query_builder().count_base()
        
        if filters:
            builder.filter(**filters)
        
        return await builder.count()
    
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
        分页查询
        
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
        builder = build_query(
            db=self.db,
            model=self.model,
            filters=filters,
            search_fields=search_fields,
            search_keyword=search_keyword,
            order_by_field=order_by,
            desc_order=desc_order,
            page=page,
            page_size=page_size,
            relations=load_relations
        )
        
        return await builder.paginated(page, page_size)
    
    async def create(self, entity: T) -> T:
        """
        创建实体
        
        Args:
            entity: 实体对象
        
        Returns:
            创建后的实体（包含生成的ID等）
        """
        self.db.add(entity)
        await self.db.flush()  # 刷新以获取ID，但不提交
        await self.db.refresh(entity)
        return entity
    
    async def update(self, entity: T) -> T:
        """
        更新实体
        
        Args:
            entity: 实体对象（已修改）
        
        Returns:
            更新后的实体
        """
        await self.db.flush()  # 刷新更改，但不提交
        await self.db.refresh(entity)
        return entity
    
    async def delete(self, entity: T) -> None:
        """
        删除实体
        
        Args:
            entity: 要删除的实体对象
        """
        await self.db.delete(entity)
        await self.db.flush()  # 刷新删除，但不提交
    
    async def exists(self, id: int) -> bool:
        """
        检查实体是否存在
        
        Args:
            id: 实体ID
        
        Returns:
            是否存在
        """
        result = await self.db.execute(
            select(func.count(self.model.id)).where(self.model.id == id)
        )
        return (result.scalar() or 0) > 0
    
    async def find_by_field(
        self,
        field_name: str,
        field_value: Any,
        load_relations: Optional[List[str]] = None
    ) -> Optional[T]:
        """
        根据字段值查找实体
        
        Args:
            field_name: 字段名
            field_value: 字段值
            load_relations: 要预加载的关联关系列表
        
        Returns:
            实体对象或None
        """
        if not hasattr(self.model, field_name):
            return None
        
        builder = self.query_builder().base()
        builder.filter(**{field_name: field_value})
        
        if load_relations:
            builder.load_relations(*load_relations)
        
        return await builder.first()
    
    async def find_all_by_field(
        self,
        field_name: str,
        field_value: Any,
        load_relations: Optional[List[str]] = None
    ) -> List[T]:
        """
        根据字段值查找所有匹配的实体
        
        Args:
            field_name: 字段名
            field_value: 字段值
            load_relations: 要预加载的关联关系列表
        
        Returns:
            实体列表
        """
        if not hasattr(self.model, field_name):
            return []
        
        builder = self.query_builder().base()
        builder.filter(**{field_name: field_value})
        
        if load_relations:
            builder.load_relations(*load_relations)
        
        return await builder.all()

