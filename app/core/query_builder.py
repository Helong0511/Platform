"""
统一查询构建器
提供通用的数据库查询构建方法，减少重复代码
"""
from typing import Optional, List, Dict, Any, Callable, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql import Select

T = TypeVar('T')


class QueryBuilder:
    """
    查询构建器
    提供链式查询构建方法
    """
    
    def __init__(self, db: AsyncSession, model: type[T]):
        """
        初始化查询构建器
        
        Args:
            db: 数据库会话
            model: 模型类
        """
        self.db = db
        self.model = model
        self._query: Optional[Select] = None
        self._count_query: Optional[Select] = None
    
    def base(self) -> 'QueryBuilder':
        """创建基础查询"""
        self._query = select(self.model)
        return self
    
    def count_base(self) -> 'QueryBuilder':
        """创建计数查询"""
        self._count_query = select(func.count(self.model.id))
        return self
    
    def filter(self, **filters: Any) -> 'QueryBuilder':
        """
        添加过滤条件
        
        Args:
            **filters: 过滤条件，键为字段名，值为过滤值
        
        Returns:
            QueryBuilder实例
        """
        if self._query is None:
            self.base()
        
        conditions = []
        for key, value in filters.items():
            if value is not None and hasattr(self.model, key):
                conditions.append(getattr(self.model, key) == value)
        
        if conditions:
            self._query = self._query.where(and_(*conditions))
        
        # 同时更新计数查询
        if self._count_query is None:
            self.count_base()
        
        if conditions:
            self._count_query = self._count_query.where(and_(*conditions))
        
        return self
    
    def search(self, search_fields: List[str], keyword: Optional[str]) -> 'QueryBuilder':
        """
        添加搜索条件（模糊匹配）
        
        Args:
            search_fields: 要搜索的字段列表
            keyword: 搜索关键词
        
        Returns:
            QueryBuilder实例
        """
        if not keyword:
            return self
        
        if self._query is None:
            self.base()
        
        search_conditions = []
        for field in search_fields:
            if hasattr(self.model, field):
                field_attr = getattr(self.model, field)
                search_conditions.append(field_attr.like(f"%{keyword}%"))
        
        if search_conditions:
            self._query = self._query.where(or_(*search_conditions))
            
            # 同时更新计数查询
            if self._count_query is None:
                self.count_base()
            self._count_query = self._count_query.where(or_(*search_conditions))
        
        return self
    
    def order_by(self, field: str, desc_order: bool = True) -> 'QueryBuilder':
        """
        添加排序条件
        
        Args:
            field: 排序字段
            desc_order: 是否降序
        
        Returns:
            QueryBuilder实例
        """
        if self._query is None:
            self.base()
        
        if hasattr(self.model, field):
            field_attr = getattr(self.model, field)
            if desc_order:
                self._query = self._query.order_by(desc(field_attr))
            else:
                self._query = self._query.order_by(asc(field_attr))
        
        return self
    
    def paginate(self, page: int = 1, page_size: int = 20) -> 'QueryBuilder':
        """
        添加分页条件
        
        Args:
            page: 页码
            page_size: 每页数量
        
        Returns:
            QueryBuilder实例
        """
        if self._query is None:
            self.base()
        
        offset = (page - 1) * page_size
        self._query = self._query.offset(offset).limit(page_size)
        
        return self
    
    def load_relations(self, *relations: str, use_selectin: bool = True) -> 'QueryBuilder':
        """
        预加载关联关系（避免N+1查询）
        
        Args:
            *relations: 关联关系名称列表
            use_selectin: 是否使用selectinload（默认True，适合一对多关系，避免重复行问题）
        
        Returns:
            QueryBuilder实例
        """
        if self._query is None:
            self.base()
        
        for relation in relations:
            if hasattr(self.model, relation):
                if use_selectin:
                    self._query = self._query.options(selectinload(getattr(self.model, relation)))
                else:
                    self._query = self._query.options(joinedload(getattr(self.model, relation)))
        
        return self
    
    async def all(self) -> List[T]:
        """
        执行查询并返回所有结果
        
        注意：当使用joinedload加载一对多关系时，会自动调用unique()去重
        
        Returns:
            结果列表
        """
        if self._query is None:
            self.base()
        
        result = await self.db.execute(self._query)
        # 当使用joinedload加载一对多关系时，SQLAlchemy要求在result上调用unique()
        # 然后再调用scalars()，而不是在scalars()之后调用unique()
        # 对于selectinload或其他情况，调用unique()也不会出错，只是没有效果
        try:
            # 检查查询中是否使用了joinedload（通过检查options）
            # 如果有joinedload，需要在result上调用unique()
            unique_result = result.unique()
            scalars_result = unique_result.scalars()
            return list(scalars_result.all())
        except Exception:
            # 如果unique()失败，回退到普通方式
            scalars_result = result.scalars()
            return list(scalars_result.all())
    
    async def first(self) -> Optional[T]:
        """
        执行查询并返回第一个结果
        
        注意：当使用joinedload加载一对多关系时，会自动调用unique()去重
        
        Returns:
            第一个结果或None
        """
        if self._query is None:
            self.base()
        
        result = await self.db.execute(self._query)
        # 当使用joinedload加载一对多关系时，SQLAlchemy要求在result上调用unique()
        # 然后再调用scalars()，而不是在scalars()之后调用unique()
        try:
            unique_result = result.unique()
            scalars_result = unique_result.scalars()
            return scalars_result.first()
        except Exception:
            # 如果unique()失败，回退到普通方式
            scalars_result = result.scalars()
            return scalars_result.first()
    
    async def count(self) -> int:
        """
        执行计数查询
        
        Returns:
            记录总数
        """
        if self._count_query is None:
            self.count_base()
        
        result = await self.db.execute(self._count_query)
        return result.scalar() or 0
    
    async def paginated(self, page: int = 1, page_size: int = 20) -> tuple[List[T], int]:
        """
        执行分页查询
        
        Args:
            page: 页码
            page_size: 每页数量
        
        Returns:
            (结果列表, 总数)
        """
        self.paginate(page, page_size)
        items = await self.all()
        total = await self.count()
        return items, total


def build_query(
    db: AsyncSession,
    model: type[T],
    filters: Optional[Dict[str, Any]] = None,
    search_fields: Optional[List[str]] = None,
    search_keyword: Optional[str] = None,
    order_by_field: Optional[str] = None,
    desc_order: bool = True,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    relations: Optional[List[str]] = None
) -> QueryBuilder:
    """
    快速构建查询的便捷函数
    
    Args:
        db: 数据库会话
        model: 模型类
        filters: 过滤条件
        search_fields: 搜索字段列表
        search_keyword: 搜索关键词
        order_by_field: 排序字段
        desc_order: 是否降序
        page: 页码
        page_size: 每页数量
        relations: 关联关系列表
    
    Returns:
        QueryBuilder实例
    """
    builder = QueryBuilder(db, model)
    builder.base()
    
    if filters:
        builder.filter(**filters)
    
    if search_fields and search_keyword:
        builder.search(search_fields, search_keyword)
    
    if order_by_field:
        builder.order_by(order_by_field, desc_order)
    
    if relations:
        builder.load_relations(*relations)
    
    if page and page_size:
        builder.paginate(page, page_size)
    
    return builder

