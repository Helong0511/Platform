"""
广告数据服务层（AdDataService）

薄编排层：CRUD 命令 + 查询模块委托。
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    AdData, Product, Client, User, UserRole, ProductAssignment, CountryInfo
)
from app.services.base_service import BaseService
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode


def join_country_info_for_ad_data(query):
    """垫片：重导出至 queries.join_helpers。"""
    from app.services.ad_data.queries.join_helpers import join_country_info_for_ad_data as _join

    return _join(query)


class AdDataService(BaseService[AdData]):
    """广告数据业务服务。"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, AdData)

    def require_admin(self, current_user: User):
        """校验当前用户是否为管理员。"""
        if current_user.role != UserRole.ADMIN:
            raise_api_exception(
                ErrorCode.FORBIDDEN,
                detail="只有管理员才能执行此操作",
            )

    async def get_ad_data_by_id(
            self,
            data_id: int,
            current_user: User
    ) -> Tuple[AdData, Product, Client, User, Optional[ProductAssignment], Optional[CountryInfo]]:
        """根据 ID 获取广告数据详情（含权限校验）。"""
        from app.services.ad_data.queries.detail_query import DetailQueryBuilder

        return await DetailQueryBuilder(self.db).fetch_and_authorize(data_id, current_user)

    async def update_ad_data(
            self,
            data_id: int,
            update_data: Dict[str, Any],
            current_user: User
    ) -> AdData:
        """更新广告数据（仅管理员）。"""
        from app.services.ad_data.commands.update_command import AdDataUpdateCommand

        return await AdDataUpdateCommand(self.db).execute(data_id, update_data, current_user)

    async def delete_ad_data(self, data_id: int, current_user: User) -> None:
        """删除单条广告数据（仅管理员）。"""
        from app.services.ad_data.commands.delete_command import AdDataDeleteCommand

        await AdDataDeleteCommand(self.db).execute(data_id, current_user)

    async def get_clients_with_data(
            self,
            current_user: User,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        from app.services.ad_data.queries.filter_options_query import FilterOptionsQuery

        return await FilterOptionsQuery(self.db).fetch_clients(current_user, start_date, end_date)

    async def get_countries_with_data(
            self,
            current_user: User,
            client_id: Optional[str] = None,
            product_id: Optional[str] = None,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            dimension: Optional[str] = None,
            ad_unit: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from app.services.ad_data.queries.filter_options_query import FilterOptionsQuery

        return await FilterOptionsQuery(self.db).fetch_countries(
            current_user, client_id, product_id, start_date, end_date, dimension, ad_unit
        )

    async def get_ad_units_with_data(
            self,
            current_user: User,
            client_id: Optional[str] = None,
            product_id: Optional[str] = None,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            dimension: Optional[str] = None,
            country_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from app.services.ad_data.queries.filter_options_query import FilterOptionsQuery

        return await FilterOptionsQuery(self.db).fetch_ad_units(
            current_user, client_id, product_id, start_date, end_date, dimension, country_code
        )

    async def get_products_with_data(
            self,
            current_user: User,
            client_id: Optional[str] = None,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        from app.services.ad_data.queries.filter_options_query import FilterOptionsQuery

        return await FilterOptionsQuery(self.db).fetch_products(
            current_user, client_id, start_date, end_date
        )

    async def get_date_range(
            self,
            current_user: User,
            client_id: Optional[int] = None
    ) -> Dict[str, Optional[str]]:
        from app.services.ad_data.queries.filter_options_query import FilterOptionsQuery

        return await FilterOptionsQuery(self.db).fetch_date_range(current_user, client_id)

    async def batch_delete_ad_data(self, data_ids: List[int], current_user: User) -> int:
        """批量删除广告数据。"""
        from app.services.ad_data.commands.delete_command import AdDataBatchDeleteCommand

        return await AdDataBatchDeleteCommand(self.db).execute(data_ids, current_user)

    async def get_ad_data_summary(
            self,
            current_user: User,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            client_id: Optional[str] = None,
            product_id: Optional[int] = None
    ) -> Dict[str, Any]:
        from app.services.ad_data.queries.summary_query import AdDataSummaryQuery

        return await AdDataSummaryQuery(self.db).fetch(
            current_user, start_date, end_date, client_id, product_id
        )

    async def get_daily_summary(
            self,
            current_user: User,
            page: int = 1,
            page_size: int = 10,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            client_id: Optional[str] = None,
            product_id: Optional[str] = None,
            country_code: Optional[str] = None,
            ad_unit: Optional[str] = None,
            dimension: Optional[str] = None,
            split_by_country: bool = False,
            sort_by: str = "date",
            sort_order: str = "desc"
    ) -> Tuple[List[Dict[str, Any]], int, Dict[str, Any]]:
        from app.services.ad_data.queries.daily_summary_query import DailySummaryQuery

        return await DailySummaryQuery(self.db).fetch(
            current_user=current_user,
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            dimension=dimension,
            split_by_country=split_by_country,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    async def get_ad_data(
            self,
            current_user: User,
            page: int = 1,
            page_size: int = 10,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            client_id: Optional[str] = None,
            product_id: Optional[str] = None,
            country_code: Optional[str] = None,
            ad_unit: Optional[str] = None,
            dimension: Optional[str] = None,
            sort_by: str = "date",
            sort_order: str = "desc"
    ) -> Tuple[List[Dict[str, Any]], int, Optional[Dict[str, Any]]]:
        from app.services.ad_data.queries.list_query import AdDataListQuery

        list_query = AdDataListQuery(self.db)
        rows, total = await list_query.fetch(
            current_user=current_user,
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            dimension=dimension,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        grand_total = await list_query.fetch_grand_totals(
            current_user=current_user,
            start_date=start_date,
            end_date=end_date,
            client_id=client_id,
            product_id=product_id,
            country_code=country_code,
            ad_unit=ad_unit,
            dimension=dimension,
        )
        return rows, total, grand_total
