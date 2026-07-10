"""
广告数据删除命令（单条 / 批量）。

在系统中的位置：
- 被 ``AdDataService.delete_ad_data`` / ``batch_delete_ad_data`` 调用
"""
import logging
from typing import List

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import is_admin
from app.models.models import AdData, User
from app.services.ad_data.queries.batch_delete_query import BatchDeleteQuery

logger = logging.getLogger(__name__)


class AdDataDeleteCommand:
    """单条广告数据删除（仅管理员）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, data_id: int, current_user: User) -> None:
        if not is_admin(current_user):
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="仅管理员可以删除广告数据",
            )

        result = await self.db.execute(select(AdData).where(AdData.id == data_id))
        ad_data = result.scalars().first()
        if not ad_data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据ID {data_id} 不存在",
            )

        await self.db.delete(ad_data)
        await self.db.flush()
        logger.info("广告数据已删除: ID=%s", data_id)


class AdDataBatchDeleteCommand:
    """批量广告数据删除（含权限过滤）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, data_ids: List[int], current_user: User) -> int:
        if not data_ids:
            raise_api_exception(
                ErrorCode.AD_DATA_EMPTY_SELECTION,
                detail="请选择要删除的广告数据。数据ID列表不能为空",
            )

        resolution = await BatchDeleteQuery(self.db).resolve(data_ids, current_user)

        if resolution.matched_count == 0:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail="未找到要删除的广告数据。请确认数据ID是否正确",
            )

        if not resolution.deletable:
            raise_api_exception(
                ErrorCode.AD_DATA_DELETE_FORBIDDEN,
                detail="您没有权限删除选中的广告数据。部分数据不属于您的客户账户",
            )

        deletable_ids = [row.id for row in resolution.deletable]
        try:
            result = await self.db.execute(delete(AdData).where(AdData.id.in_(deletable_ids)))
            deleted_count = result.rowcount
            await self.db.flush()
            logger.info(
                "Batch deleted %s ad data records by %s",
                deleted_count,
                current_user.username,
            )
            return deleted_count
        except Exception as e:
            await self.db.rollback()
            logger.error("批量删除广告数据失败: %s", str(e), exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"批量删除广告数据失败：{str(e)}。请稍后重试或联系管理员",
            )
