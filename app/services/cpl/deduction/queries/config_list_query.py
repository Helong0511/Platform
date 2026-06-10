"""
扣减配置分页列表查询。
"""
from typing import List, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.models.models import ConversionDeductionConfig, Offer


class DeductionConfigListQuery:
    """扣减配置列表查询（含广告主级 + 其 Offer 子配置筛选）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch(
        self,
        page: int = 1,
        page_size: int = 20,
        level: Optional[str] = None,
        is_active: Optional[bool] = None,
        keyword: Optional[str] = None,
        advertiser_id: Optional[int] = None,
    ) -> Tuple[List[ConversionDeductionConfig], int]:
        conditions = self._build_conditions(level, is_active, advertiser_id)

        count_query = select(func.count()).select_from(ConversionDeductionConfig)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total = (await self.db.execute(count_query)).scalar() or 0

        query = select(ConversionDeductionConfig)
        if conditions:
            query = query.where(and_(*conditions))
        query = (
            query.order_by(
                ConversionDeductionConfig.priority.desc(),
                ConversionDeductionConfig.created_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(
                joinedload(ConversionDeductionConfig.advertiser),
                joinedload(ConversionDeductionConfig.offer),
                joinedload(ConversionDeductionConfig.publisher),
            )
        )

        configs = (await self.db.execute(query)).unique().scalars().all()

        if keyword:
            configs, total = self._filter_by_keyword(configs, keyword)

        return configs, total

    def _build_conditions(
        self,
        level: Optional[str],
        is_active: Optional[bool],
        advertiser_id: Optional[int],
    ):
        conditions = []
        if level:
            if level == "advertiser":
                conditions.append(ConversionDeductionConfig.advertiser_id.isnot(None))
            elif level == "offer":
                conditions.append(ConversionDeductionConfig.offer_id.isnot(None))
            elif level == "publisher":
                conditions.append(ConversionDeductionConfig.publisher_id.isnot(None))

        if is_active is not None:
            conditions.append(ConversionDeductionConfig.is_active == is_active)

        if advertiser_id:
            offer_subquery = select(Offer.id).where(Offer.advertiser_id == advertiser_id).subquery()
            conditions.append(
                or_(
                    ConversionDeductionConfig.advertiser_id == advertiser_id,
                    ConversionDeductionConfig.offer_id.in_(offer_subquery),
                )
            )
        return conditions

    def _filter_by_keyword(
        self,
        configs: List[ConversionDeductionConfig],
        keyword: str,
    ) -> Tuple[List[ConversionDeductionConfig], int]:
        keyword_lower = keyword.lower()
        filtered = []
        for config in configs:
            target_name = None
            if config.advertiser:
                target_name = config.advertiser.advertiser_name
            elif config.offer:
                target_name = config.offer.offer_name
            elif config.publisher:
                target_name = config.publisher.publisher_name

            if target_name and keyword_lower in target_name.lower():
                filtered.append(config)
        return filtered, len(filtered)
