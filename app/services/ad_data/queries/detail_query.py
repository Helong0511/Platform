"""
广告数据详情查询构建器。

功能说明：
- 按主键或业务键查询单条/批量广告明细
- 预加载关联产品、客户信息，减少 N+1 查询

在系统中的位置：
- 被 ``AdDataService`` 详情与编辑接口调用

注意事项：
1. 详情查询需校验当前用户是否有权访问对应产品
2. 大字段（备注等）仅在详情接口 select，列表接口应省略
"""
import logging
from typing import Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import load_only

from app.core.query_utils import (
    product_assignment_join_condition,
    check_use_assignment_table,
    join_country_info as join_country_info_util
)
from app.core.utils import unpack_ad_data_query_result
from app.models.models import AdData, Product, Client, User, ProductAssignment, CountryInfo

logger = logging.getLogger(__name__)


def join_country_info_for_ad_data(query):
    """
    为广告数据查询左关联国家信息表。

    通过 AdData.country_code 与 CountryInfo 关联，统一处理排序规则冲突，
    避免不同字符集/排序规则导致的 JOIN 异常。

    Args:
        query: 已包含 AdData 的 SQLAlchemy 查询对象

    Returns:
        附加了 CountryInfo 左连接后的查询对象
    """
    return join_country_info_util(query, AdData.country_code)


class DetailQueryBuilder:
    """
    广告数据详情查询构建器。

    封装单条记录的多表 JOIN 逻辑，屏蔽产品分配历史表与旧关联方式的差异，
    对外统一返回四元组 (ad_data, product, client, user)。
    """

    def __init__(self, db: AsyncSession):
        """
        初始化构建器。

        Args:
            db: 异步数据库会话
        """
        self.db = db

    async def build_detail_query(
            self,
            data_id: int,
            current_user
    ) -> Optional[Tuple[AdData, Product, Client, User]]:
        """
        构建并执行详情查询，返回单条广告数据及其关联实体。

        查询链路：AdData → Product → (ProductAssignment?) → Client → User → CountryInfo

        Args:
            data_id: 广告数据主键 ID
            current_user: 当前登录用户（预留权限扩展，当前查询未使用）

        Returns:
            成功时返回 (ad_data, product, client, user) 四元组；
            记录不存在或解包失败时返回 None。
        """

        # ── 1. 判断客户归属模式 ──────────────────────────────────────
        use_assignment_table = await check_use_assignment_table(self.db)

        if use_assignment_table:
            # ── 2a. 产品分配历史表模式 ─────────────────────────────────
            # 按广告日期匹配 ProductAssignment，确定当时归属的客户
            query = select(AdData, Product, Client, User, ProductAssignment, CountryInfo)
            # 仅加载 Client 必要字段，减少数据传输
            query = query.options(load_only(
                Client.id, Client.user_id, Client.company_name, Client.contact_person,
                Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
            ))
            query = query.join(Product, AdData.product_id == Product.id)
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
            # ── 2b. 旧模式：产品直接绑定客户 ───────────────────────────
            query = select(AdData, Product, Client, User, CountryInfo)
            query = query.options(load_only(
                Client.id, Client.user_id, Client.company_name, Client.contact_person,
                Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
            ))
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)

        # ── 3. 公共关联与过滤条件 ──────────────────────────────────────
        query = query.join(User, Client.user_id == User.id)
        query = join_country_info_for_ad_data(query)
        query = query.where(AdData.id == data_id)
        query = query.where(Product.is_active == True)

        # ── 4. 执行查询 ────────────────────────────────────────────────
        result = await self.db.execute(query)
        data = result.unique().first()

        if not data:
            return None

        # ── 5. 解包多表查询结果 ────────────────────────────────────────
        # unpack 根据 use_assignment_table 自动处理 5/6 列元组差异
        try:
            ad_data, product, client, user, assignment, country_info = unpack_ad_data_query_result(
                data, use_assignment_table
            )
            return ad_data, product, client, user
        except Exception as e:
            logger.error(f"解构数据失败：{str(e)}")
            return None
