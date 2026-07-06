"""
广告数据唯一性约束预检查询。

约束：uq_ad_data_identity（日期 + 产品 + 国家 + 广告单元 + 数据来源 + 报表维度）

在系统中的位置：
- 被 ``AdDataService.update_ad_data`` 在写入前调用
"""
from datetime import date, datetime
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.country_code import build_ad_data_country_equality

from app.models.models import AdData, CountryInfo, Product


class AdDataUniquenessQuery:
    """广告数据维度唯一性冲突检测。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _day_bounds(ad_date) -> Tuple[datetime, datetime]:
        if isinstance(ad_date, datetime):
            return (
                ad_date.replace(hour=0, minute=0, second=0, microsecond=0),
                ad_date.replace(hour=23, minute=59, second=59, microsecond=999999),
            )
        return (
            datetime.combine(ad_date, datetime.min.time()),
            datetime.combine(ad_date, datetime.max.time()),
        )

    @staticmethod
    def _country_condition(country_code: Optional[str]):
        return build_ad_data_country_equality(AdData.country_code, country_code)

    async def find_conflict(
        self,
        ad_data: AdData,
        product_id: int,
        country_code: str,
        ad_unit: str,
        *,
        data_source: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> Optional[AdData]:
        date_start, date_end = self._day_bounds(ad_data.date)
        resolved_source = data_source if data_source is not None else (ad_data.data_source or "legacy")
        resolved_type = report_type if report_type is not None else (ad_data.report_type or "legacy")
        query = select(AdData).where(
            AdData.id != ad_data.id,
            AdData.date >= date_start,
            AdData.date <= date_end,
            AdData.product_id == product_id,
            AdData.ad_unit == ad_unit,
            AdData.data_source == resolved_source,
            AdData.report_type == resolved_type,
            self._country_condition(country_code),
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def build_conflict_message(
        self,
        existing: AdData,
        ad_data: AdData,
        product_id: int,
        country_code: str,
    ) -> str:
        country_name = await self._resolve_country_name(existing.country_code or country_code)
        product_name = await self._resolve_product_name(product_id)
        date_value = self._normalize_date(ad_data.date)
        ad_unit_label = existing.ad_unit or "（空）"
        return (
            f"更新失败：已存在相同的记录（日期={date_value}，产品={product_name}，"
            f"国家={country_name}，广告单元={ad_unit_label}）。"
            f"请先删除或修改冲突的记录（ID: {existing.id}）"
        )

    async def build_integrity_conflict_message(
        self,
        ad_data: AdData,
        product_id: int,
        country_code: str,
        ad_unit: str,
        conflict_info: str = "",
    ) -> str:
        country_name = await self._resolve_country_name(country_code)
        product_name = await self._resolve_product_name(product_id)
        date_value = self._normalize_date(ad_data.date)
        suffix = f"{conflict_info}" if conflict_info else ""
        return (
            f"更新失败：已存在相同的记录（日期={date_value}，产品={product_name}，"
            f"国家={country_name}，广告单元={ad_unit or '（空）'}）。"
            f"同一日期、产品、国家和广告单元的组合必须唯一，请先删除或修改冲突的记录。{suffix}"
        )

    async def _resolve_country_name(self, country_code: Optional[str]) -> str:
        if not country_code:
            return "无国家"
        if country_code == "ZZ":
            return "全部区域"
        result = await self.db.execute(
            select(CountryInfo).where(CountryInfo.alpha_2_code == country_code)
        )
        country_info = result.scalar_one_or_none()
        return country_info.country_name_zh if country_info else country_code

    async def _resolve_product_name(self, product_id: int) -> str:
        result = await self.db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        return product.name if product else f"产品ID {product_id}"

    @staticmethod
    def _normalize_date(ad_date) -> date:
        if isinstance(ad_date, datetime):
            return ad_date.date()
        if hasattr(ad_date, "date"):
            return ad_date.date()
        return ad_date
