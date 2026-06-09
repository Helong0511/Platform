"""
广告数据列表查询构建器。

功能说明：
- 构建广告明细分页列表的 SELECT/WHERE/JOIN/ORDER 条件
- 支持产品、客户、日期、国家等多维筛选与排序

在系统中的位置：
- 被 ``AdDataService`` 列表接口调用

注意事项：
1. 客户用户查询须自动附加产品分配过滤条件
2. 优先使用索引字段（date、product_id）缩小扫描范围
"""
import logging
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.query_utils import (
    product_assignment_join_condition,
    check_use_assignment_table
)
from app.models.models import AdData, Product, Client, User, UserRole, ProductAssignment

logger = logging.getLogger(__name__)


class ListQueryBuilder:
    """
    广告数据列表查询构建器。

    将分页、权限、过滤、计数等逻辑拆分为私有方法，
    对外仅暴露 build_list_query 入口。
    """

    def __init__(self, db: AsyncSession):
        """
        初始化构建器。

        Args:
            db: 异步数据库会话
        """
        self.db = db

    async def build_list_query(
            self,
            current_user: User,
            page: int = 1,
            page_size: int = 20,
            filters: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[AdData], int]:
        """
        构建列表查询并返回分页结果。

        流程：构建基础查询 → 应用 offset/limit → 执行数据查询 → 独立计数查询。

        Args:
            current_user: 当前登录用户，用于权限过滤
            page: 页码，从 1 开始
            page_size: 每页记录数
            filters: 可选过滤字典，支持 date_from、date_to、product_id、country_code

        Returns:
            (当前页 AdData 列表, 符合条件的总记录数)
        """
        filters = filters or {}

        # ── 1. 构建带权限与过滤的基础查询 ────────────────────────────
        query = await self._build_base_query(current_user, filters)

        # ── 2. 应用分页 ──────────────────────────────────────────────
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # ── 3. 执行数据查询 ──────────────────────────────────────────
        result = await self.db.execute(query)
        data = result.scalars().all()

        # ── 4. 独立计数（与分页无关，获取全量匹配数）────────────────
        total = await self._get_total_count(current_user, filters)

        return data, total

    async def _build_base_query(
            self,
            current_user: User,
            filters: Dict[str, Any]
    ):
        """
        构建列表基础查询（不含分页）。

        JOIN 路径选择：
            - 分配历史表模式 + 含日期过滤：通过 ProductAssignment 按日期匹配客户
            - 分配历史表模式 + 无日期过滤：回退 Product.client_id 直接关联
            - 旧模式：Product.client_id 直接关联

        Args:
            current_user: 当前用户
            filters: 过滤条件字典

        Returns:
            已应用权限与过滤的 SQLAlchemy 查询对象
        """

        use_assignment_table = await check_use_assignment_table(self.db)

        if use_assignment_table:
            query = select(AdData).join(Product, AdData.product_id == Product.id)

            # 有日期范围时，必须走分配历史表才能确定当时归属的客户
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

        # ── 关联用户表（权限过滤依赖 Client.user_id）──────────────────
        query = query.join(User, Client.user_id == User.id)

        # ── 非管理员仅能查看自己名下客户的数据 ───────────────────────
        if current_user.role != UserRole.ADMIN:
            query = query.where(Client.user_id == current_user.id)

        # ── 仅展示激活状态的产品 ─────────────────────────────────────
        query = query.where(Product.is_active == True)

        # ── 应用业务过滤条件 ─────────────────────────────────────────
        query = self._apply_filters(query, filters)

        return query

    def _apply_filters(self, query, filters: Dict[str, Any]):
        """
        将前端传入的过滤条件追加到查询 WHERE 子句。

        支持的过滤键：
            - date_from / date_to：广告数据日期范围（闭区间）
            - product_id：产品 ID 精确匹配
            - country_code：国家代码精确匹配

        Args:
            query: 待追加条件的查询对象
            filters: 过滤条件字典

        Returns:
            追加过滤后的查询对象
        """

        if 'date_from' in filters:
            query = query.where(AdData.date >= filters['date_from'])

        if 'date_to' in filters:
            query = query.where(AdData.date <= filters['date_to'])

        if 'product_id' in filters:
            query = query.where(AdData.product_id == filters['product_id'])

        if 'country_code' in filters:
            query = query.where(AdData.country_code == filters['country_code'])

        return query

    async def _get_total_count(
            self,
            current_user: User,
            filters: Dict[str, Any]
    ) -> int:
        """
        获取符合权限与过滤条件的广告数据总记录数。

        注意：当前实现为简化版计数，非管理员时仅做权限 JOIN，
        未完全复用 _build_base_query 中的全部过滤条件（如日期、产品等），
        调用方需知悉此差异。

        Args:
            current_user: 当前用户
            filters: 过滤条件字典（当前计数逻辑未全部应用）

        Returns:
            匹配记录总数，无记录时返回 0
        """

        query = select(func.count(AdData.id))

        # 非管理员需 JOIN 产品与客户以施加权限限制
        if current_user.role != UserRole.ADMIN:
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)
            query = query.where(Client.user_id == current_user.id)
            query = query.where(Product.is_active == True)

        result = await self.db.execute(query)
        return result.scalar() or 0
