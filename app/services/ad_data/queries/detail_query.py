"""
广告数据详情查询构建器。

功能说明：
- 按主键查询单条广告明细及关联实体
- 预加载产品、客户、用户、分配记录与国家信息

在系统中的位置：
- 被 ``AdDataService.get_ad_data_by_id`` 调用
"""
import logging
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.query_utils import check_use_assignment_table
from app.core.security import is_admin
from app.core.utils import unpack_ad_data_query_result
from app.models.models import AdData, Client, CountryInfo, Product, ProductAssignment, User
from app.services.ad_data.queries.join_helpers import (
    CLIENT_LOAD_ONLY,
    join_country_info_for_ad_data,
    join_product_and_client,
)

logger = logging.getLogger(__name__)


class DetailQueryBuilder:
    """广告数据单条详情查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_by_id(
        self,
        data_id: int,
    ) -> Optional[
        Tuple[AdData, Product, Client, User, Optional[ProductAssignment], Optional[CountryInfo]]
    ]:
        """
        按 ID 查询详情及全部关联实体。

        Returns:
            六元组；记录不存在或解包失败时返回 None
        """
        use_assignment_table = await check_use_assignment_table(self.db)

        if use_assignment_table:
            query = select(AdData, Product, Client, User, ProductAssignment, CountryInfo)
        else:
            query = select(AdData, Product, Client, User, CountryInfo)

        query = query.options(CLIENT_LOAD_ONLY)
        query = join_product_and_client(query, use_assignment_table)
        query = query.join(User, Client.user_id == User.id)
        query = join_country_info_for_ad_data(query)
        query = query.where(AdData.id == data_id, Product.is_active == True)

        data = (await self.db.execute(query)).unique().first()
        if not data:
            return None

        try:
            return unpack_ad_data_query_result(data, use_assignment_table)
        except Exception as e:
            logger.error("解构详情数据失败：%s", str(e))
            return None

    async def build_detail_query(self, data_id: int, current_user) -> Optional[Tuple[AdData, Product, Client, User]]:
        """兼容旧接口：返回四元组（不含 assignment / country_info）。"""
        row = await self.fetch_by_id(data_id)
        if not row:
            return None
        ad_data, product, client, user, _assignment, _country_info = row
        return ad_data, product, client, user

    async def fetch_and_authorize(
        self,
        data_id: int,
        current_user: User,
    ) -> Tuple[AdData, Product, Client, User, Optional[ProductAssignment], Optional[CountryInfo]]:
        """查询详情并校验关联完整性及访问权限。"""
        row = await self.fetch_by_id(data_id)
        if not row:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据ID {data_id} 不存在",
            )

        ad_data, product, client, user, assignment, country_info = row

        if not product:
            raise_api_exception(
                ErrorCode.AD_DATA_PRODUCT_NOT_FOUND,
                detail=f"广告数据关联的产品ID {ad_data.product_id} 不存在",
            )
        if not client:
            raise_api_exception(
                ErrorCode.CLIENT_NOT_FOUND,
                detail=f"广告数据关联的客户ID {product.client_id if product else '未知'} 不存在",
            )
        if not user:
            raise_api_exception(
                ErrorCode.USER_NOT_FOUND,
                detail=f"广告数据关联的用户ID {client.user_id if client else '未知'} 不存在",
            )
        if not is_admin(current_user) and client.user_id != current_user.id:
            raise_api_exception(
                ErrorCode.AD_DATA_NO_PERMISSION,
                detail=f"您没有权限访问广告数据ID {data_id}，该数据不属于您的客户账户",
            )
        return ad_data, product, client, user, assignment, country_info
