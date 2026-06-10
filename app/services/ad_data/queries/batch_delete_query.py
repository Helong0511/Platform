"""
广告数据批量删除前的归属查询。

功能说明：
- 按 ID 列表加载 AdData 及客户归属
- 按用户角色过滤出可删除记录

在系统中的位置：
- 被 ``AdDataService.batch_delete_ad_data`` 调用
"""
import logging
from dataclasses import dataclass
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.query_utils import check_use_assignment_table
from app.core.security import is_admin
from app.models.models import AdData, Client, Product, ProductAssignment, User
from app.services.ad_data.queries.join_helpers import join_product_and_client

logger = logging.getLogger(__name__)


@dataclass
class BatchDeleteResolution:
    """批量删除解析结果。"""

    matched_count: int
    deletable: List[AdData]


class BatchDeleteQuery:
    """批量删除权限过滤查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve(
        self,
        data_ids: List[int],
        current_user: User,
    ) -> BatchDeleteResolution:
        use_assignment_table = await check_use_assignment_table(self.db)

        if use_assignment_table:
            query = select(AdData, Product, Client, ProductAssignment)
        else:
            query = select(AdData, Product, Client)

        query = join_product_and_client(query, use_assignment_table)
        query = query.where(AdData.id.in_(data_ids))

        all_data = (await self.db.execute(query)).unique().all()
        if not all_data:
            return BatchDeleteResolution(matched_count=0, deletable=[])

        if is_admin(current_user):
            if use_assignment_table:
                deletable = [ad_data for ad_data, _, _, _ in all_data]
            else:
                deletable = [ad_data for ad_data, _, _ in all_data]
            return BatchDeleteResolution(matched_count=len(all_data), deletable=deletable)

        deletable = []
        for row in all_data:
            if use_assignment_table:
                ad_data, _product, client, _assignment = row
            else:
                ad_data, _product, client = row

            if client.user_id == current_user.id:
                deletable.append(ad_data)
            else:
                logger.warning(
                    "用户 %s 尝试删除无权访问的数据 ID: %s",
                    current_user.username,
                    ad_data.id,
                )
        return BatchDeleteResolution(matched_count=len(all_data), deletable=deletable)
