"""
扣减日志聚合统计查询。
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import ConversionDeductionLog


class DeductionStatsQuery:
    """扣减日志 KPI 与分组统计。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: Optional[str] = None,
        advertiser_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        start_dt, end_dt = self._parse_date_range(start_date, end_date)
        conditions = self._build_conditions(
            start_dt, end_dt, advertiser_id, offer_id, publisher_id
        )

        stats_row = (
            await self.db.execute(
                select(
                    func.sum(ConversionDeductionLog.original_volume).label("original_volume"),
                    func.sum(ConversionDeductionLog.deducted_volume).label("deducted_volume"),
                    func.sum(ConversionDeductionLog.final_volume).label("final_volume"),
                    func.sum(ConversionDeductionLog.original_amount).label("original_amount"),
                    func.sum(ConversionDeductionLog.deducted_amount).label("deducted_amount"),
                    func.sum(ConversionDeductionLog.final_amount).label("final_amount"),
                ).where(and_(*conditions))
            )
        ).first()

        original_volume = stats_row.original_volume or 0
        deducted_volume = stats_row.deducted_volume or 0
        final_volume = stats_row.final_volume or 0
        original_amount = float(stats_row.original_amount or 0)
        deducted_amount = float(stats_row.deducted_amount or 0)
        final_amount = float(stats_row.final_amount or 0)

        volume_deduction_ratio = deducted_volume / original_volume if original_volume > 0 else 0.0
        amount_deduction_ratio = deducted_amount / original_amount if original_amount > 0 else 0.0

        items = []
        if group_by and group_by != "time":
            items = await self._fetch_group_items(conditions, group_by)

        return {
            "original_volume": int(original_volume),
            "deducted_volume": int(deducted_volume),
            "final_volume": int(final_volume),
            "volume_deduction_ratio": volume_deduction_ratio,
            "original_amount": original_amount,
            "deducted_amount": deducted_amount,
            "final_amount": final_amount,
            "amount_deduction_ratio": amount_deduction_ratio,
            "items": items,
        }

    def _parse_date_range(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> tuple[datetime, datetime]:
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = datetime.now() - timedelta(days=30)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        else:
            end_dt = datetime.now()
        return start_dt, end_dt

    def _build_conditions(
        self,
        start_dt: datetime,
        end_dt: datetime,
        advertiser_id: Optional[int],
        offer_id: Optional[int],
        publisher_id: Optional[int],
    ):
        conditions = [
            ConversionDeductionLog.created_at >= start_dt,
            ConversionDeductionLog.created_at < end_dt,
        ]
        if advertiser_id:
            conditions.append(ConversionDeductionLog.advertiser_id == advertiser_id)
        if offer_id:
            conditions.append(ConversionDeductionLog.offer_id == offer_id)
        if publisher_id:
            conditions.append(ConversionDeductionLog.publisher_id == publisher_id)
        return conditions

    async def _fetch_group_items(self, conditions, group_by: str):
        group_fields = []
        if group_by == "advertiser":
            group_fields = [ConversionDeductionLog.advertiser_id]
        elif group_by == "offer":
            group_fields = [ConversionDeductionLog.offer_id]
        elif group_by == "publisher":
            group_fields = [ConversionDeductionLog.publisher_id]

        if not group_fields:
            return []

        group_result = await self.db.execute(
            select(
                *group_fields,
                func.sum(ConversionDeductionLog.original_volume).label("original_volume"),
                func.sum(ConversionDeductionLog.deducted_volume).label("deducted_volume"),
                func.sum(ConversionDeductionLog.final_volume).label("final_volume"),
                func.sum(ConversionDeductionLog.original_amount).label("original_amount"),
                func.sum(ConversionDeductionLog.deducted_amount).label("deducted_amount"),
                func.sum(ConversionDeductionLog.final_amount).label("final_amount"),
            )
            .where(and_(*conditions))
            .group_by(*group_fields)
        )

        items = []
        for row in group_result:
            item_data = {
                "original_volume": int(row.original_volume or 0),
                "deducted_volume": int(row.deducted_volume or 0),
                "final_volume": int(row.final_volume or 0),
                "original_amount": float(row.original_amount or 0),
                "deducted_amount": float(row.deducted_amount or 0),
                "final_amount": float(row.final_amount or 0),
                "volume_deduction_ratio": (row.deducted_volume or 0) / (row.original_volume or 1)
                if row.original_volume
                else 0.0,
                "amount_deduction_ratio": (row.deducted_amount or 0) / (row.original_amount or 1)
                if row.original_amount
                else 0.0,
            }
            if group_by == "advertiser" and row.advertiser_id:
                item_data["advertiser_id"] = row.advertiser_id
            elif group_by == "offer" and row.offer_id:
                item_data["offer_id"] = row.offer_id
            elif group_by == "publisher" and row.publisher_id:
                item_data["publisher_id"] = row.publisher_id
            items.append(item_data)
        return items
