"""
广告数据日标准冻结与倒扣对比（方案 B：日期+产品+来源）。

- 每天 00:30 冻结「昨天」快照（请求数 + 收益扣前）
- 入库后对已冻结历史日：现库汇总 vs 标准，任一项跌≥阈值告警
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import get_app_now_naive
from app.models.ad_data_health import (
    AdDataDayBaseline,
    AdDataHealthAlert,
    AdDataHealthSettings,
)
from app.models.models import AdData, Product

logger = logging.getLogger(__name__)

ALERT_BASELINE_DROP = "baseline_drop"
ALERT_MISSING = "missing"
ALERT_STREAK = "streak"
ALERT_TODAY_GAP = "today_gap"
ALERT_DOD_DROP = "dod_drop"

METRIC_REQUEST = "request_count"
METRIC_REVENUE_BEFORE = "revenue_before"
METRIC_REVENUE_AFTER = "revenue_after"


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class HealthSettingsView:
    drop_ratio: float = 0.02
    request_floor: int = 100
    revenue_floor: float = 1.0
    enable_baseline_drop: bool = True
    enable_missing: bool = True
    enable_streak: bool = True
    enable_today_gap: bool = True
    enable_dod_drop: bool = True
    enable_telegram: bool = True
    cooldown_hours: int = 24


async def get_or_create_settings(db: AsyncSession) -> AdDataHealthSettings:
    row = await db.get(AdDataHealthSettings, 1)
    if row:
        return row
    row = AdDataHealthSettings(id=1, updated_at=get_app_now_naive())
    db.add(row)
    await db.flush()
    return row


async def load_settings_view(db: AsyncSession) -> HealthSettingsView:
    row = await get_or_create_settings(db)
    return HealthSettingsView(
        drop_ratio=_as_float(row.drop_ratio),
        request_floor=_as_int(row.request_floor),
        revenue_floor=_as_float(row.revenue_floor),
        enable_baseline_drop=bool(row.enable_baseline_drop),
        enable_missing=bool(row.enable_missing),
        enable_streak=bool(row.enable_streak),
        enable_today_gap=bool(row.enable_today_gap),
        enable_dod_drop=bool(row.enable_dod_drop),
        enable_telegram=bool(row.enable_telegram),
        cooldown_hours=max(_as_int(row.cooldown_hours), 0),
    )


async def update_settings(
    db: AsyncSession,
    *,
    payload: dict[str, Any],
) -> AdDataHealthSettings:
    row = await get_or_create_settings(db)
    mapping = {
        "drop_ratio": "drop_ratio",
        "request_floor": "request_floor",
        "revenue_floor": "revenue_floor",
        "enable_baseline_drop": "enable_baseline_drop",
        "enable_missing": "enable_missing",
        "enable_streak": "enable_streak",
        "enable_today_gap": "enable_today_gap",
        "enable_dod_drop": "enable_dod_drop",
        "enable_telegram": "enable_telegram",
        "cooldown_hours": "cooldown_hours",
    }
    for key, attr in mapping.items():
        if key in payload and payload[key] is not None:
            setattr(row, attr, payload[key])
    row.updated_at = get_app_now_naive()
    await db.flush()
    return row


async def aggregate_ad_data_for_baseline(
    db: AsyncSession,
    *,
    stat_date: date,
    data_sources: Optional[Sequence[str]] = None,
) -> list[dict[str, Any]]:
    """
    按 日期+产品+来源 汇总请求数与扣前收益。

    优先只用 report_type=cross；若某 (product, source) 无 cross，再取该源当日全部行。
    """
    filters = [AdData.date == stat_date]
    if data_sources:
        filters.append(AdData.data_source.in_(list(data_sources)))

    cross_q = (
        select(
            AdData.product_id,
            AdData.data_source,
            func.coalesce(func.sum(AdData.request_count), 0).label("request_count"),
            func.coalesce(func.sum(AdData.revenue_before_deduct), 0).label(
                "revenue_before"
            ),
            func.count(AdData.id).label("row_count"),
        )
        .where(*filters, AdData.report_type == "cross")
        .group_by(AdData.product_id, AdData.data_source)
    )
    cross_rows = (await db.execute(cross_q)).mappings().all()
    cross_keys = {(int(r["product_id"]), str(r["data_source"])) for r in cross_rows}

    all_q = (
        select(
            AdData.product_id,
            AdData.data_source,
            func.coalesce(func.sum(AdData.request_count), 0).label("request_count"),
            func.coalesce(func.sum(AdData.revenue_before_deduct), 0).label(
                "revenue_before"
            ),
            func.count(AdData.id).label("row_count"),
        )
        .where(*filters)
        .group_by(AdData.product_id, AdData.data_source)
    )
    all_rows = (await db.execute(all_q)).mappings().all()

    out: dict[tuple[int, str], dict[str, Any]] = {}
    for r in cross_rows:
        key = (int(r["product_id"]), str(r["data_source"]))
        out[key] = dict(r)
    for r in all_rows:
        key = (int(r["product_id"]), str(r["data_source"]))
        if key not in cross_keys:
            out[key] = dict(r)
    return list(out.values())


async def freeze_baseline_for_date(
    db: AsyncSession,
    *,
    stat_date: date,
    force: bool = False,
    batch_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    冻结某日标准。force=False 时若已有任意标准行则跳过。
    """
    batch = batch_id or f"freeze-{stat_date.isoformat()}-{uuid.uuid4().hex[:8]}"
    existing = await db.execute(
        select(func.count())
        .select_from(AdDataDayBaseline)
        .where(AdDataDayBaseline.stat_date == stat_date)
    )
    count_existing = int(existing.scalar() or 0)
    if count_existing > 0 and not force:
        return {
            "stat_date": stat_date.isoformat(),
            "skipped": True,
            "reason": "已存在标准，未强制重冻",
            "existing_rows": count_existing,
            "inserted": 0,
            "batch_id": batch,
        }

    if force and count_existing > 0:
        from sqlalchemy import delete

        await db.execute(
            delete(AdDataDayBaseline).where(AdDataDayBaseline.stat_date == stat_date)
        )

    aggs = await aggregate_ad_data_for_baseline(db, stat_date=stat_date)
    now = get_app_now_naive()
    inserted = 0
    for row in aggs:
        db.add(
            AdDataDayBaseline(
                stat_date=stat_date,
                product_id=int(row["product_id"]),
                data_source=str(row["data_source"] or "unknown"),
                request_count=_as_int(row["request_count"]),
                revenue_before=_as_float(row["revenue_before"]),
                row_count=_as_int(row["row_count"]),
                frozen_at=now,
                freeze_batch_id=batch,
            )
        )
        inserted += 1
    await db.flush()
    logger.info(
        "冻结标准日 %s：写入 %d 行 force=%s batch=%s",
        stat_date,
        inserted,
        force,
        batch,
    )
    return {
        "stat_date": stat_date.isoformat(),
        "skipped": False,
        "existing_rows": count_existing,
        "inserted": inserted,
        "batch_id": batch,
        "force": force,
    }


async def _recently_alerted(
    db: AsyncSession,
    *,
    alert_type: str,
    stat_date: date,
    product_id: int,
    data_source: str,
    metric: str,
    cooldown_hours: int,
) -> bool:
    if cooldown_hours <= 0:
        return False
    since = get_app_now_naive() - timedelta(hours=cooldown_hours)
    q = await db.execute(
        select(AdDataHealthAlert.id)
        .where(
            AdDataHealthAlert.alert_type == alert_type,
            AdDataHealthAlert.stat_date == stat_date,
            AdDataHealthAlert.product_id == product_id,
            AdDataHealthAlert.data_source == data_source,
            AdDataHealthAlert.metric == metric,
            AdDataHealthAlert.created_at >= since,
        )
        .limit(1)
    )
    return q.scalar_one_or_none() is not None


async def compare_date_against_baseline(
    db: AsyncSession,
    *,
    stat_date: date,
    data_source: Optional[str] = None,
    settings: Optional[HealthSettingsView] = None,
    batch_id: Optional[str] = None,
    persist: bool = True,
) -> list[dict[str, Any]]:
    """
    将现库汇总与标准对比；请求数或扣前收益跌≥阈值则生成告警项。
    """
    cfg = settings or await load_settings_view(db)
    if not cfg.enable_baseline_drop:
        return []

    base_filters = [AdDataDayBaseline.stat_date == stat_date]
    if data_source:
        base_filters.append(AdDataDayBaseline.data_source == data_source)
    baselines = (
        await db.execute(select(AdDataDayBaseline).where(*base_filters))
    ).scalars().all()
    if not baselines:
        return []

    sources = list({b.data_source for b in baselines})
    current_rows = await aggregate_ad_data_for_baseline(
        db, stat_date=stat_date, data_sources=sources
    )
    current_map = {
        (int(r["product_id"]), str(r["data_source"])): r for r in current_rows
    }

    name_rows = (
        await db.execute(
            select(Product.id, Product.name).where(
                Product.id.in_([b.product_id for b in baselines])
            )
        )
    ).all()
    names = {int(i): str(n) for i, n in name_rows}

    batch = batch_id or f"baseline-cmp-{uuid.uuid4().hex[:8]}"
    alerts: list[dict[str, Any]] = []

    for b in baselines:
        key = (int(b.product_id), str(b.data_source))
        cur = current_map.get(key) or {
            "request_count": 0,
            "revenue_before": 0,
            "row_count": 0,
        }
        product_name = names.get(int(b.product_id), f"产品#{b.product_id}")
        pairs = [
            (
                METRIC_REQUEST,
                _as_float(b.request_count),
                _as_float(cur["request_count"]),
                cfg.request_floor,
            ),
            (
                METRIC_REVENUE_BEFORE,
                _as_float(b.revenue_before),
                _as_float(cur["revenue_before"]),
                cfg.revenue_floor,
            ),
        ]
        for metric, base_v, cur_v, floor in pairs:
            if base_v < floor:
                continue
            if cur_v >= base_v:
                continue
            drop = (base_v - cur_v) / base_v
            if drop + 1e-12 < cfg.drop_ratio:
                continue
            if await _recently_alerted(
                db,
                alert_type=ALERT_BASELINE_DROP,
                stat_date=stat_date,
                product_id=int(b.product_id),
                data_source=str(b.data_source),
                metric=metric,
                cooldown_hours=cfg.cooldown_hours,
            ):
                continue
            metric_label = "请求数" if metric == METRIC_REQUEST else "收益(扣前)"
            detail = (
                f"倒扣：{stat_date.isoformat()} {product_name} [{b.data_source}] "
                f"{metric_label} 标准 {base_v:.2f} → 现库 {cur_v:.2f}（{drop:.1%}）"
            )
            item = {
                "alert_type": ALERT_BASELINE_DROP,
                "stat_date": stat_date,
                "product_id": int(b.product_id),
                "product_name": product_name,
                "data_source": str(b.data_source),
                "metric": metric,
                "baseline_value": base_v,
                "current_value": cur_v,
                "drop_ratio": drop,
                "detail": detail,
                "batch_id": batch,
            }
            alerts.append(item)
            if persist:
                db.add(
                    AdDataHealthAlert(
                        alert_type=ALERT_BASELINE_DROP,
                        stat_date=stat_date,
                        product_id=int(b.product_id),
                        product_name=product_name,
                        data_source=str(b.data_source),
                        metric=metric,
                        baseline_value=Decimal(str(round(base_v, 4))),
                        current_value=Decimal(str(round(cur_v, 4))),
                        drop_ratio=Decimal(str(round(drop, 6))),
                        detail=detail,
                        batch_id=batch,
                        notified=False,
                        created_at=get_app_now_naive(),
                    )
                )
    if persist and alerts:
        await db.flush()
    return alerts


async def compare_frozen_dates_after_import(
    db: AsyncSession,
    *,
    touched_dates: Sequence[date],
    today: date,
    data_source: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """入库后：对「早于今天且已有标准」的日期做倒扣对比。"""
    cfg = await load_settings_view(db)
    if not cfg.enable_baseline_drop:
        return []
    all_alerts: list[dict[str, Any]] = []
    for d in sorted(set(touched_dates)):
        if d >= today:
            continue
        exists = await db.execute(
            select(AdDataDayBaseline.id)
            .where(AdDataDayBaseline.stat_date == d)
            .limit(1)
        )
        if exists.scalar_one_or_none() is None:
            continue
        all_alerts.extend(
            await compare_date_against_baseline(
                db,
                stat_date=d,
                data_source=data_source,
                settings=cfg,
                batch_id=batch_id,
                persist=True,
            )
        )
    return all_alerts


def format_baseline_drop_telegram(alerts: list[dict[str, Any]]) -> Optional[str]:
    if not alerts:
        return None
    lines = [
        "🔄 倒扣巡查：相对日标准下跌≥阈值",
        "",
        f"共 {len(alerts)} 条",
        "",
    ]
    for a in alerts[:80]:
        lines.append(f"  • {a.get('detail') or ''}")
    if len(alerts) > 80:
        lines.append(f"  … 另有 {len(alerts) - 80} 条省略")
    return "\n".join(lines)


async def list_baselines(
    db: AsyncSession,
    *,
    stat_date: Optional[date] = None,
    product_id: Optional[int] = None,
    data_source: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    filters = []
    if stat_date:
        filters.append(AdDataDayBaseline.stat_date == stat_date)
    if product_id:
        filters.append(AdDataDayBaseline.product_id == product_id)
    if data_source:
        filters.append(AdDataDayBaseline.data_source == data_source)

    count_q = select(func.count()).select_from(AdDataDayBaseline)
    if filters:
        count_q = count_q.where(*filters)
    total = int((await db.execute(count_q)).scalar() or 0)

    q = (
        select(AdDataDayBaseline, Product.name)
        .join(Product, Product.id == AdDataDayBaseline.product_id, isouter=True)
        .order_by(
            AdDataDayBaseline.stat_date.desc(),
            AdDataDayBaseline.data_source,
            Product.name,
        )
        .limit(limit)
        .offset(offset)
    )
    if filters:
        q = q.where(*filters)
    rows = (await db.execute(q)).all()
    items = []
    for b, name in rows:
        items.append(
            {
                "id": b.id,
                "stat_date": b.stat_date.isoformat() if b.stat_date else None,
                "product_id": b.product_id,
                "product_name": name or f"产品#{b.product_id}",
                "data_source": b.data_source,
                "request_count": b.request_count,
                "revenue_before": _as_float(b.revenue_before),
                "row_count": b.row_count,
                "frozen_at": b.frozen_at.isoformat(sep=" ") if b.frozen_at else None,
                "freeze_batch_id": b.freeze_batch_id,
            }
        )
    return items, total


async def list_alerts(
    db: AsyncSession,
    *,
    stat_date: Optional[date] = None,
    alert_type: Optional[str] = None,
    product_id: Optional[int] = None,
    notified: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    filters = []
    if stat_date:
        filters.append(AdDataHealthAlert.stat_date == stat_date)
    if alert_type:
        filters.append(AdDataHealthAlert.alert_type == alert_type)
    if product_id:
        filters.append(AdDataHealthAlert.product_id == product_id)
    if notified is not None:
        filters.append(AdDataHealthAlert.notified == notified)

    count_q = select(func.count()).select_from(AdDataHealthAlert)
    if filters:
        count_q = count_q.where(*filters)
    total = int((await db.execute(count_q)).scalar() or 0)

    q = select(AdDataHealthAlert).order_by(AdDataHealthAlert.created_at.desc())
    if filters:
        q = q.where(*filters)
    q = q.limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    items = []
    for a in rows:
        items.append(
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "stat_date": a.stat_date.isoformat() if a.stat_date else None,
                "product_id": a.product_id,
                "product_name": a.product_name,
                "data_source": a.data_source,
                "metric": a.metric,
                "baseline_value": _as_float(a.baseline_value)
                if a.baseline_value is not None
                else None,
                "current_value": _as_float(a.current_value)
                if a.current_value is not None
                else None,
                "drop_ratio": _as_float(a.drop_ratio)
                if a.drop_ratio is not None
                else None,
                "detail": a.detail,
                "batch_id": a.batch_id,
                "notified": bool(a.notified),
                "created_at": a.created_at.isoformat(sep=" ") if a.created_at else None,
            }
        )
    return items, total
