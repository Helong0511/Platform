"""
扣减执行日志分页查询。
"""
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.models.models import ConversionDeductionLog


class DeductionLogsQuery:
    """扣减日志列表查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch(
        self,
        page: int = 1,
        page_size: int = 20,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        conversion_id: Optional[int] = None,
        click_id: Optional[str] = None,
    ) -> Tuple[List[ConversionDeductionLog], int]:
        conditions = self._build_conditions(
            start_date,
            end_date,
            advertiser_id,
            offer_id,
            publisher_id,
            conversion_id,
            click_id,
        )

        count_query = select(func.count()).select_from(ConversionDeductionLog)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total = (await self.db.execute(count_query)).scalar() or 0

        query = select(ConversionDeductionLog)
        if conditions:
            query = query.where(and_(*conditions))
        query = (
            query.order_by(ConversionDeductionLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(
                joinedload(ConversionDeductionLog.advertiser),
                joinedload(ConversionDeductionLog.offer),
                joinedload(ConversionDeductionLog.publisher),
            )
        )

        logs = (await self.db.execute(query)).unique().scalars().all()
        return logs, total

    def _build_conditions(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
        advertiser_id: Optional[int],
        offer_id: Optional[int],
        publisher_id: Optional[int],
        conversion_id: Optional[int],
        click_id: Optional[str],
    ):
        conditions = []
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            conditions.append(ConversionDeductionLog.created_at >= start_dt)
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            conditions.append(ConversionDeductionLog.created_at < end_dt)
        if advertiser_id:
            conditions.append(ConversionDeductionLog.advertiser_id == advertiser_id)
        if offer_id:
            conditions.append(ConversionDeductionLog.offer_id == offer_id)
        if publisher_id:
            conditions.append(ConversionDeductionLog.publisher_id == publisher_id)
        if conversion_id:
            conditions.append(ConversionDeductionLog.conversion_id == conversion_id)
        if click_id:
            conditions.append(ConversionDeductionLog.click_id == click_id)
        return conditions
