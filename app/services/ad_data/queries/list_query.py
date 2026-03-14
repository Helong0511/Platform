"""
列表查询构建器

构建广告数据列表查询
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from app.models.models import AdData, Product, Client, User, UserRole, ProductAssignment
from app.core.query_utils import (
    product_assignment_join_condition,
    check_use_assignment_table,
    apply_date_range_filter
)

logger = logging.getLogger(__name__)


class ListQueryBuilder:
    """列表查询构建器"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def build_list_query(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[AdData], int]:
        """
        构建列表查询
        
        Args:
            current_user: 当前用户
            page: 页码
            page_size: 每页数量
            filters: 过滤条件
        
        Returns:
            tuple: (数据列表，总数)
        """
        filters = filters or {}
        
        # 构建基础查询
        query = await self._build_base_query(current_user, filters)
        
        # 应用分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        # 执行查询
        result = await self.db.execute(query)
        data = result.scalars().all()
        
        # 获取总数
        total = await self._get_total_count(current_user, filters)
        
        return data, total
    
    async def _build_base_query(
        self,
        current_user: User,
        filters: Dict[str, Any]
    ):
        """构建基础查询"""
        
        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)
        
        if use_assignment_table:
            query = select(AdData).join(Product, AdData.product_id == Product.id)
            
            # 关联 ProductAssignment
            if 'date_from' in filters or 'date_to' in filters:
                date_from = filters.get('date_from')
                date_to = filters.get('date_to')
                query = query.join(
                    ProductAssignment,
                    and_(
                        ProductAssignment.product_id == Product.id,
                        product_assignment_join_condition(
                            AdData.date,
                            ProductAssignment.start_date,
                            ProductAssignment.end_date
                        )
                    )
                )
                query = query.join(Client, ProductAssignment.client_id == Client.id)
            else:
                query = query.join(Client, Product.client_id == Client.id)
        else:
            query = select(AdData).join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)
        
        # 关联 User
        query = query.join(User, Client.user_id == User.id)
        
        # 权限过滤
        if current_user.role != UserRole.ADMIN:
            query = query.where(Client.user_id == current_user.id)
        
        # 产品状态过滤
        query = query.where(Product.is_active == True)
        
        # 应用其他过滤条件
        query = self._apply_filters(query, filters)
        
        return query
    
    def _apply_filters(self, query, filters: Dict[str, Any]):
        """应用过滤条件"""
        
        # 日期范围过滤
        if 'date_from' in filters:
            query = query.where(AdData.date >= filters['date_from'])
        
        if 'date_to' in filters:
            query = query.where(AdData.date <= filters['date_to'])
        
        # 产品 ID 过滤
        if 'product_id' in filters:
            query = query.where(AdData.product_id == filters['product_id'])
        
        # 国家代码过滤
        if 'country_code' in filters:
            query = query.where(AdData.country_code == filters['country_code'])
        
        return query
    
    async def _get_total_count(
        self,
        current_user: User,
        filters: Dict[str, Any]
    ) -> int:
        """获取总数"""
        
        query = select(func.count(AdData.id))
        
        # 简化查询获取总数
        if current_user.role != UserRole.ADMIN:
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)
            query = query.where(Client.user_id == current_user.id)
            query = query.where(Product.is_active == True)
        
        result = await self.db.execute(query)
        return result.scalar() or 0
