"""
扣减日志聚合统计查询。
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.utils import get_app_now_naive
from app.models.models import ConversionDeductionLog

UNKNOWN_CURRENCY = "LEGACY_UNKNOWN"
UNKNOWN_CURRENCY_SOURCE = "legacy_unknown"


def _normalized_currency(value: Optional[str]) -> str:
    return str(value).strip().upper() if value and str(value).strip() else UNKNOWN_CURRENCY


def _normalized_currency_source(value: Optional[str]) -> str:
    return str(value).strip().lower() if value and str(value).strip() else UNKNOWN_CURRENCY_SOURCE


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

        currency_rows = (
            await self.db.execute(
                select(
                    func.upper(func.trim(func.coalesce(func.nullif(ConversionDeductionLog.currency, ""), UNKNOWN_CURRENCY))).label("currency"),
                    func.lower(func.trim(func.coalesce(func.nullif(ConversionDeductionLog.currency_source, ""), UNKNOWN_CURRENCY_SOURCE))).label("currency_source"),
                    func.sum(ConversionDeductionLog.original_volume).label("original_volume"),
                    func.sum(ConversionDeductionLog.deducted_volume).label("deducted_volume"),
                    func.sum(ConversionDeductionLog.final_volume).label("final_volume"),
                    func.sum(ConversionDeductionLog.original_amount).label("original_amount"),
                    func.sum(ConversionDeductionLog.deducted_amount).label("deducted_amount"),
                    func.sum(ConversionDeductionLog.final_amount).label("final_amount"),
                )
                .where(and_(*conditions))
                .group_by(
                    func.upper(func.trim(func.coalesce(func.nullif(ConversionDeductionLog.currency, ""), UNKNOWN_CURRENCY))),
                    func.lower(func.trim(func.coalesce(func.nullif(ConversionDeductionLog.currency_source, ""), UNKNOWN_CURRENCY_SOURCE))),
                )
                .order_by("currency", "currency_source")
            )
        ).all()

        currency_summaries = []
        original_volume = deducted_volume = final_volume = 0
        for row in currency_rows:
            row_original_volume = int(row.original_volume or 0)
            row_deducted_volume = int(row.deducted_volume or 0)
            row_final_volume = int(row.final_volume or 0)
            row_original_amount = Decimal(row.original_amount or 0)
            row_deducted_amount = Decimal(row.deducted_amount or 0)
            row_final_amount = Decimal(row.final_amount or 0)
            original_volume += row_original_volume
            deducted_volume += row_deducted_volume
            final_volume += row_final_volume
            currency_summaries.append({
                "currency": _normalized_currency(row.currency),
                "currency_source": _normalized_currency_source(row.currency_source),
                "original_amount": row_original_amount,
                "deducted_amount": row_deducted_amount,
                "final_amount": row_final_amount,
                "amount_deduction_ratio": (
                    row_deducted_amount / row_original_amount if row_original_amount > 0 else Decimal('0')
                ),
                "original_volume": row_original_volume,
                "deducted_volume": row_deducted_volume,
                "final_volume": row_final_volume,
            })

        volume_deduction_ratio = deducted_volume / original_volume if original_volume > 0 else 0.0
        # 仅当查询结果只有一种币种时保留兼容性金额总计；多币种时禁止跨币种相加。
        if len(currency_summaries) == 1:
            only_currency = currency_summaries[0]
            original_amount = only_currency["original_amount"]
            deducted_amount = only_currency["deducted_amount"]
            final_amount = only_currency["final_amount"]
            amount_deduction_ratio = only_currency["amount_deduction_ratio"]
        elif not currency_summaries:
            original_amount = deducted_amount = final_amount = Decimal('0')
            amount_deduction_ratio = Decimal('0')
        else:
            original_amount = deducted_amount = final_amount = None
            amount_deduction_ratio = None

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
            "currency_summaries": currency_summaries,
            "items": items,
        }

    def _parse_date_range(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> tuple[datetime, datetime]:
        app_now = get_app_now_naive()
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = app_now - timedelta(days=30)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        else:
            end_dt = app_now
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
        group_fields.extend([
            func.upper(func.trim(func.coalesce(func.nullif(ConversionDeductionLog.currency, ""), UNKNOWN_CURRENCY))).label("currency"),
            func.lower(func.trim(func.coalesce(func.nullif(ConversionDeductionLog.currency_source, ""), UNKNOWN_CURRENCY_SOURCE))).label("currency_source"),
        ])

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
                "currency": _normalized_currency(row.currency),
                "currency_source": _normalized_currency_source(row.currency_source),
                "original_volume": int(row.original_volume or 0),
                "deducted_volume": int(row.deducted_volume or 0),
                "final_volume": int(row.final_volume or 0),
                "original_amount": Decimal(row.original_amount or 0),
                "deducted_amount": Decimal(row.deducted_amount or 0),
                "final_amount": Decimal(row.final_amount or 0),
                "volume_deduction_ratio": (row.deducted_volume or 0) / (row.original_volume or 1)
                if row.original_volume
                else 0.0,
                "amount_deduction_ratio": Decimal(row.deducted_amount or 0) / Decimal(row.original_amount or 1)
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
