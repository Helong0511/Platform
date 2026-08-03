"""
同日 API 国家维度与广告单元维度扣后收益一致性检查。

规则（业务确认）：
- 同一产品 + 同一天同时存在纯国家行与纯广告单元行
- 两边 SUM(revenue_after_deduct) 不完全相等 → 告警，人工核对
- 日汇总仍只取一套（默认优先国家）；Excel 与 API 同日仍相加，不在此互斥
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AdData, Product
from app.services.ad_data.queries.dimension_filter import (
    _ad_unit_only_row_condition,
    _country_only_row_condition,
)

_REVENUE_QUANT = Decimal("0.0001")


def _as_revenue(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(_REVENUE_QUANT)


async def find_country_unit_revenue_mismatches(
    db: AsyncSession,
    *,
    start_date: date,
    end_date: date,
    product_ids: Optional[Sequence[int]] = None,
    limit: int = 15,
) -> tuple[list[dict[str, Any]], int]:
    """
    查找同产品同日「国家维度合计收益 ≠ 广告单元维度合计收益」的记录。

    Returns:
        (不一致明细列表, 不一致组数)
    """
    date_filters = [
        AdData.date >= start_date,
        AdData.date <= end_date,
    ]
    if product_ids:
        date_filters.append(AdData.product_id.in_(list(product_ids)))

    country_subq = (
        select(
            AdData.product_id.label("product_id"),
            AdData.date.label("data_date"),
            func.coalesce(func.sum(AdData.revenue_after_deduct), 0).label(
                "country_revenue"
            ),
            func.count(AdData.id).label("country_rows"),
        )
        .where(
            *date_filters,
            _country_only_row_condition(AdData.country_code, AdData.ad_unit),
        )
        .group_by(AdData.product_id, AdData.date)
        .subquery("country_rev")
    )

    unit_subq = (
        select(
            AdData.product_id.label("product_id"),
            AdData.date.label("data_date"),
            func.coalesce(func.sum(AdData.revenue_after_deduct), 0).label(
                "unit_revenue"
            ),
            func.count(AdData.id).label("unit_rows"),
        )
        .where(
            *date_filters,
            _ad_unit_only_row_condition(AdData.country_code, AdData.ad_unit),
        )
        .group_by(AdData.product_id, AdData.date)
        .subquery("unit_rev")
    )

    joined = (
        select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            country_subq.c.data_date,
            country_subq.c.country_revenue,
            country_subq.c.country_rows,
            unit_subq.c.unit_revenue,
            unit_subq.c.unit_rows,
        )
        .select_from(country_subq)
        .join(
            unit_subq,
            (country_subq.c.product_id == unit_subq.c.product_id)
            & (country_subq.c.data_date == unit_subq.c.data_date),
        )
        .join(Product, Product.id == country_subq.c.product_id)
        .order_by(country_subq.c.data_date.desc(), Product.name.asc())
    )

    rows = (await db.execute(joined)).all()
    mismatches: list[dict[str, Any]] = []
    for r in rows:
        country_rev = _as_revenue(r.country_revenue)
        unit_rev = _as_revenue(r.unit_revenue)
        if country_rev == unit_rev:
            continue
        mismatches.append(
            {
                "product_id": int(r.product_id),
                "product_name": r.product_name or "未知产品",
                "data_date": (
                    r.data_date.isoformat()
                    if hasattr(r.data_date, "isoformat")
                    else str(r.data_date)
                ),
                "country_revenue": float(country_rev),
                "unit_revenue": float(unit_rev),
                "diff_revenue": float(country_rev - unit_rev),
                "country_rows": int(r.country_rows or 0),
                "unit_rows": int(r.unit_rows or 0),
            }
        )

    total = len(mismatches)
    return mismatches[:limit], total


def format_country_unit_mismatch_telegram_message(
    *,
    notify_title: str,
    mismatches: list[dict[str, Any]],
    total: int,
) -> str:
    """格式化国家/广告单元同日收益不一致 Telegram 告警。"""
    lines = [
        "⚠️ 国家与广告单元同日收益不一致",
        "",
        f"来源: {notify_title}",
        f"需人工核对的产品×日期: {total} 组",
        "规则: 同日同时有国家维度与广告单元维度，且扣后收益合计不等",
        "日汇总默认仍优先取国家维度；本告警仅提醒核对，不自动改数",
        "",
        "明细（产品 | 日期 | 国家收益 | 单元收益 | 差额）:",
    ]
    for item in mismatches:
        lines.append(
            f"• {item['product_name']} | {item['data_date']} | "
            f"{item['country_revenue']:.4f} | {item['unit_revenue']:.4f} | "
            f"{item['diff_revenue']:+.4f}"
            f"（国家{item['country_rows']}行/单元{item['unit_rows']}行）"
        )
    if total > len(mismatches):
        lines.append(f"• … 其余 {total - len(mismatches)} 组未列出")
    lines.append("")
    lines.append("请人工核对上游报表后决定保留/修正哪一侧数据。")
    return "\n".join(lines)
