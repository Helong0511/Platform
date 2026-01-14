"""
分页查询工具模块

提供通用的分页查询函数，减少重复代码
"""
from typing import TypeVar, Optional, List, Callable, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from sqlalchemy.sql import Select

from app.core.constants import MAX_PAGE_SIZE

# 泛型类型变量
ModelType = TypeVar('ModelType')


async def paginate_query(
    db: AsyncSession,
    query: Select,
    page: int = 1,
    page_size: int = 10,
    order_by: Optional[Any] = None,
    conditions: Optional[List] = None,
    model_class: Optional[type] = None
) -> tuple[List[Any], int]:
    """
    通用分页查询函数
    
    执行分页查询并返回结果列表和总数
    
    Args:
        db: 数据库会话
        query: SQLAlchemy查询对象
        page: 页码（从1开始）
        page_size: 每页数量（最大不超过MAX_PAGE_SIZE）
        order_by: 排序字段（可选）
        conditions: 查询条件列表（可选，如果提供会应用到查询中）
        model_class: 模型类（用于计算总数，如果query已经包含select则不需要）
    
    Returns:
        tuple: (结果列表, 总数)
    
    Example:
        ```python
        # 基本用法
        query = select(User)
        users, total = await paginate_query(
            db=db,
            query=query,
            page=1,
            page_size=10,
            order_by=User.created_at.desc()
        )
        
        # 带条件查询
        conditions = [User.is_active == True]
        query = select(User)
        users, total = await paginate_query(
            db=db,
            query=query,
            page=1,
            page_size=10,
            conditions=conditions,
            order_by=User.created_at.desc()
        )
        ```
    """
    # 限制page_size不超过最大值
    page_size = min(page_size, MAX_PAGE_SIZE)
    
    # 应用查询条件
    if conditions:
        query = query.where(and_(*conditions))
    
    # 计算总数
    # 如果query已经包含select，需要从query中提取模型类
    if model_class is None:
        # 尝试从query中提取模型类
        # 这适用于 query = select(Model) 的情况
        if hasattr(query, 'column_descriptions') and query.column_descriptions:
            model_class = query.column_descriptions[0].get('entity')
    
    if model_class:
        # 使用模型类构建count查询
        count_query = select(func.count()).select_from(model_class)
    else:
        # 使用原始query构建count查询
        count_query = select(func.count()).select_from(query.subquery())
    
    if conditions:
        count_query = count_query.where(and_(*conditions))
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 应用排序
    if order_by is not None:
        query = query.order_by(order_by)
    
    # 应用分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # 执行查询
    result = await db.execute(query)
    items = result.scalars().all()
    
    return items, total
