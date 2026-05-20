"""
广告数据服务拆分草稿（未完成，勿接入 API）。

生产请使用 ``app.services.ad_data.service.AdDataService``。
"""
import logging
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.models.models import AdData, Product, Client, User, UserRole
from app.services.ad_data.queries.detail_query import DetailQueryBuilder
from app.services.ad_data.queries.list_query import ListQueryBuilder
from app.services.ad_data.validators import AdDataValidator
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)


class AdDataServiceStub(BaseService[AdData]):
    """广告数据服务（草稿，未覆盖 get_ad_data / daily_summary 等）"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, AdData)

    async def get_ad_data_by_id(
            self,
            data_id: int,
            current_user: User
    ) -> Tuple[AdData, Product, Client, User]:
        """根据 ID 获取广告数据详情"""

        # 构建查询
        query_builder = DetailQueryBuilder(self.db)
        data = await query_builder.build_detail_query(data_id, current_user)

        if not data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据 ID {data_id} 不存在"
            )

        # 解包数据
        ad_data, product, client, user = data

        # 权限检查
        if user.role != UserRole.ADMIN and client.user_id != current_user.id:
            raise_api_exception(
                ErrorCode.AD_DATA_NO_PERMISSION,
                detail=f"您没有权限访问广告数据 ID {data_id}"
            )

        return ad_data, product, client, user

    async def get_ad_data_list(
            self,
            current_user: User,
            page: int = 1,
            page_size: int = 20,
            filters: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[AdData], int]:
        """获取广告数据列表"""

        query_builder = ListQueryBuilder(self.db)
        return await query_builder.build_list_query(current_user, page, page_size, filters or {})

    async def update_ad_data(
            self,
            data_id: int,
            update_data: Dict[str, Any],
            current_user: User
    ) -> AdData:
        """更新广告数据"""

        # 1. 验证数据
        is_admin = current_user.role == UserRole.ADMIN
        valid, errors = AdDataValidator.validate_update_data(update_data, is_admin)

        if not valid:
            raise_api_exception(
                ErrorCode.VALIDATION_ERROR,
                detail="; ".join(errors)
            )

        # 2. 查询现有数据
        query = select(AdData).where(AdData.id == data_id)
        result = await self.db.execute(query)
        ad_data = result.scalars().first()

        if not ad_data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据 ID {data_id} 不存在"
            )

        # 3. 更新字段
        for field, value in update_data.items():
            if hasattr(ad_data, field):
                setattr(ad_data, field, value)

        # 4. 重新计算比率
        if hasattr(ad_data, 'calculate_rates'):
            ad_data.calculate_rates()

        # 5. 保存
        try:
            await self.db.commit()
            await self.db.refresh(ad_data)
            logger.info(f"广告数据已更新：id={data_id}")
            return ad_data
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新广告数据失败：{e}", exc_info=True)
            raise_api_exception(
                ErrorCode.INTERNAL_ERROR,
                detail=f"更新失败：{str(e)}"
            )

    async def delete_ad_data(
            self,
            data_id: int,
            current_user: User
    ) -> bool:
        """删除广告数据"""

        # 权限检查
        if current_user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="仅管理员可以删除广告数据"
            )

        # 查询数据
        query = select(AdData).where(AdData.id == data_id)
        result = await self.db.execute(query)
        ad_data = result.scalars().first()

        if not ad_data:
            raise_api_exception(
                ErrorCode.AD_DATA_NOT_FOUND,
                detail=f"广告数据 ID {data_id} 不存在"
            )

        # 删除
        try:
            await self.db.delete(ad_data)
            await self.db.commit()
            logger.info(f"广告数据已删除：id={data_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除广告数据失败：{e}", exc_info=True)
            raise_api_exception(
                ErrorCode.INTERNAL_ERROR,
                detail=f"删除失败：{str(e)}"
            )
