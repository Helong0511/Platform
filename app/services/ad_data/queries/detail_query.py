"""
详情查询构建器

构建广告数据详情查询
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
    """辅助函数：统一处理 CountryInfo 的 JOIN"""
    return join_country_info_util(query, AdData.country_code)


class DetailQueryBuilder:
    """详情查询构建器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_detail_query(
            self,
            data_id: int,
            current_user
    ) -> Optional[Tuple[AdData, Product, Client, User]]:
        """
        构建详情查询
        
        Args:
            data_id: 广告数据 ID
            current_user: 当前用户
        
        Returns:
            tuple: (ad_data, product, client, user) 或 None
        """

        # 检查是否使用产品分配历史表
        use_assignment_table = await check_use_assignment_table(self.db)

        if use_assignment_table:
            # 使用产品分配历史表
            query = select(AdData, Product, Client, User, ProductAssignment, CountryInfo)
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
            # 旧的查询方式
            query = select(AdData, Product, Client, User, CountryInfo)
            query = query.options(load_only(
                Client.id, Client.user_id, Client.company_name, Client.contact_person,
                Client.phone, Client.address, Client.is_active, Client.created_at, Client.updated_at
            ))
            query = query.join(Product, AdData.product_id == Product.id)
            query = query.join(Client, Product.client_id == Client.id)

        query = query.join(User, Client.user_id == User.id)
        query = join_country_info_for_ad_data(query)
        query = query.where(AdData.id == data_id)
        query = query.where(Product.is_active == True)

        result = await self.db.execute(query)
        data = result.unique().first()

        if not data:
            return None

        # 解包数据
        try:
            ad_data, product, client, user, assignment, country_info = unpack_ad_data_query_result(
                data, use_assignment_table
            )
            return ad_data, product, client, user
        except Exception as e:
            logger.error(f"解构数据失败：{str(e)}")
            return None
