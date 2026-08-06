"""
广告数据日级健康巡检执行器：缺数/断档/昨有今无/日环比 + 倒扣(vs标准)。
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.telegram import send_telegram_notify_async
from app.core.telegram_utils import split_long_message
from app.core.utils import get_app_now, get_app_now_naive
from app.models.ad_data_health import AdDataHealthAlert
from app.models.models import AdData, Product
from app.services.ad_data import baseline_service as bs
from app.services.ad_data.health_check import (
    AdDataHealthConfig,
    ProductDayAgg,
    TODAY_GAP_ALERT_AFTER_HOUR,
    build_daily_map,
    detect_ad_data_health,
    format_health_report_text,
    should_alert_today_gap,
    _coerce_date,
)
from app.services.ad_data.watch_products import (
    is_watch_window_active,
    parse_watch_products_text,
    resolve_watch_product_ids,
)

logger = logging.getLogger(__name__)


async def _load_product_daily_map(
    db: AsyncSession,
    *,
    start: date,
    end: date,
    extra_product_ids: Optional[Sequence[int]] = None,
) -> tuple[dict[int, str], dict[int, dict[date, ProductDayAgg]]]:
    names = {
        int(i): str(n)
        for i, n in (
            await db.execute(select(Product.id, Product.name).where(Product.is_active == True))  # noqa: E712
        ).all()
    }
    # 重点关注可能匹配到未启用产品，仍需纳入名称与日汇总
    if extra_product_ids:
        missing = [int(p) for p in extra_product_ids if int(p) not in names]
        if missing:
            for i, n in (
                await db.execute(
                    select(Product.id, Product.name).where(Product.id.in_(missing))
                )
            ).all():
                names[int(i)] = str(n)
    rows = (
        await db.execute(
            select(
                AdData.product_id,
                AdData.date,
                AdData.request_count,
                AdData.revenue_after_deduct,
            ).where(AdData.date >= start, AdData.date <= end)
        )
    ).all()
    # 聚合成日级：row_count + revenue_after（日环比/缺数用结算收益）
    from collections import defaultdict

    bucket: dict[tuple[int, date], list] = defaultdict(lambda: [0, 0.0])
    for pid, d, req, rev in rows:
        day = _coerce_date(d)
        key = (int(pid), day)
        bucket[key][0] += 1
        bucket[key][1] += float(rev or 0)

    flat = [
        {
            "product_id": pid,
            "data_date": day,
            "row_count": cnt,
            "revenue_after": rev,
        }
        for (pid, day), (cnt, rev) in bucket.items()
    ]
    return names, build_daily_map(flat)


async def _persist_scan_alerts(
    db: AsyncSession,
    *,
    report,
    settings_view: bs.HealthSettingsView,
    batch_id: str,
) -> int:
    """把巡检报告中的缺数/断档/今无/日环比写入告警表。"""
    created = 0

    async def _add(
        *,
        alert_type: str,
        stat_date: date,
        product_id: int,
        product_name: str,
        metric: str,
        baseline_value: Optional[float],
        current_value: Optional[float],
        drop_ratio: Optional[float],
        detail: str,
        data_source: str = "",
    ) -> None:
        nonlocal created
        if await bs._recently_alerted(
            db,
            alert_type=alert_type,
            stat_date=stat_date,
            product_id=product_id,
            data_source=data_source,
            metric=metric,
            cooldown_hours=settings_view.cooldown_hours,
        ):
            return
        db.add(
            AdDataHealthAlert(
                alert_type=alert_type,
                stat_date=stat_date,
                product_id=product_id,
                product_name=product_name,
                data_source=data_source,
                metric=metric,
                baseline_value=None
                if baseline_value is None
                else Decimal(str(round(baseline_value, 4))),
                current_value=None
                if current_value is None
                else Decimal(str(round(current_value, 4))),
                drop_ratio=None
                if drop_ratio is None
                else Decimal(str(round(drop_ratio, 6))),
                detail=detail,
                batch_id=batch_id,
                notified=False,
                created_at=get_app_now_naive(),
            )
        )
        created += 1

    if settings_view.enable_streak:
        for item in report.streak_breaks:
            await _add(
                alert_type=bs.ALERT_STREAK,
                stat_date=item.check_date,
                product_id=item.product_id,
                product_name=item.product_name,
                metric="presence",
                baseline_value=float(item.streak_before_check),
                current_value=0,
                drop_ratio=1.0,
                detail=(
                    f"连续 {item.streak_before_check} 天有数据后 "
                    f"{item.check_date.isoformat()} 没有数据"
                ),
            )
    if settings_view.enable_missing:
        for item in report.missing_yesterday:
            await _add(
                alert_type=bs.ALERT_MISSING,
                stat_date=item.check_date,
                product_id=item.product_id,
                product_name=item.product_name,
                metric="presence",
                baseline_value=float(item.days_with_data_in_lookback),
                current_value=0,
                drop_ratio=1.0,
                detail=f"{item.check_date.isoformat()} 没有数据（监控池）",
            )
    if settings_view.enable_today_gap:
        for item in report.today_gaps:
            await _add(
                alert_type=bs.ALERT_TODAY_GAP,
                stat_date=item.today,
                product_id=item.product_id,
                product_name=item.product_name,
                metric="presence",
                baseline_value=float(item.yesterday_rows),
                current_value=0,
                drop_ratio=1.0,
                detail=(
                    f"{item.yesterday.isoformat()} 有数据，"
                    f"{item.today.isoformat()} 还没有拉到"
                ),
            )
    if settings_view.enable_dod_drop:
        for item in report.revenue_drops:
            await _add(
                alert_type=bs.ALERT_DOD_DROP,
                stat_date=item.yesterday,
                product_id=item.product_id,
                product_name=item.product_name,
                metric=bs.METRIC_REVENUE_AFTER,
                baseline_value=item.revenue_day_before,
                current_value=item.revenue_yesterday,
                drop_ratio=item.drop_ratio,
                detail=(
                    f"日环比结算收益 {item.day_before.isoformat()} "
                    f"{item.revenue_day_before:.2f} → {item.yesterday.isoformat()} "
                    f"{item.revenue_yesterday:.2f}（{item.drop_ratio:.1%}）"
                ),
            )
    await db.flush()
    return created


async def run_daily_health_scan(
    db: AsyncSession,
    *,
    today: Optional[date] = None,
    send_telegram: Optional[bool] = None,
) -> dict[str, Any]:
    """执行完整日级巡检并可选发 Telegram。"""
    now = get_app_now()
    today = today or now.date()
    yesterday = today - timedelta(days=1)
    cfg_view = await bs.load_settings_view(db)
    batch_id = f"health-{today.isoformat()}-{uuid.uuid4().hex[:8]}"

    watch_lines = parse_watch_products_text(cfg_view.watch_products)
    force_ids: list[int] = []
    watch_active, watch_window_status = is_watch_window_active(
        today,
        effective_date=cfg_view.watch_effective_date,
        expire_date=cfg_view.watch_expire_date,
    )
    if watch_lines and watch_active:
        matched = await resolve_watch_product_ids(db, watch_lines=watch_lines)
        for pairs in matched.values():
            force_ids.extend(pid for pid, _ in pairs)
        force_ids = sorted(set(force_ids))

    lookback = 7
    start = yesterday - timedelta(days=lookback - 1)
    names, daily_map = await _load_product_daily_map(
        db, start=start, end=today, extra_product_ids=force_ids
    )

    report = detect_ad_data_health(
        today=today,
        product_names=names,
        daily_map=daily_map,
        config=AdDataHealthConfig(
            lookback_days=lookback,
            active_days=3,
            streak_days=3,
            drop_ratio=cfg_view.drop_ratio,
            revenue_floor=cfg_view.revenue_floor,
        ),
        force_product_ids=force_ids or None,
    )
    report.backfill_date = yesterday

    # 中午前不报「昨有今无」：01:00 定时巡检常见误报
    today_gap_suppressed = False
    suppressed_today_gap_count = 0
    if not should_alert_today_gap(now):
        suppressed_today_gap_count = len(report.today_gaps)
        if suppressed_today_gap_count:
            today_gap_suppressed = True
            report.today_gaps = []
            logger.info(
                "健康巡检：当前 %02d:%02d 早于 %02d:00，跳过「昨有今无」%d 条",
                now.hour,
                now.minute,
                TODAY_GAP_ALERT_AFTER_HOUR,
                suppressed_today_gap_count,
            )

    # 倒扣：昨天若已有标准，现库 vs 标准
    baseline_alerts: list[dict[str, Any]] = []
    if cfg_view.enable_baseline_drop:
        baseline_alerts = await bs.compare_date_against_baseline(
            db,
            stat_date=yesterday,
            settings=cfg_view,
            batch_id=batch_id,
            persist=True,
        )
        report.backfill_drops = []  # 文案改用 baseline 段；兼容旧字段清空 live 倒扣
        report.backfill_note = (
            f"倒扣对比标准日 {yesterday.isoformat()}：{len(baseline_alerts)} 条跌幅告警"
            if baseline_alerts
            else f"倒扣对比标准日 {yesterday.isoformat()}：无≥{cfg_view.drop_ratio:.0%}跌幅"
        )

    persisted = await _persist_scan_alerts(
        db, report=report, settings_view=cfg_view, batch_id=batch_id
    )

    text = format_health_report_text(
        report,
        baseline_alert_count=len(baseline_alerts),
        today_gap_suppressed=today_gap_suppressed,
        today_gap_suppress_hour=TODAY_GAP_ALERT_AFTER_HOUR,
    )
    if baseline_alerts:
        extra = bs.format_baseline_drop_telegram(baseline_alerts)
        if extra:
            text = text.rstrip() + "\n\n" + extra + "\n"

    do_send = cfg_view.enable_telegram if send_telegram is None else send_telegram
    telegram_sent = False
    if do_send and (report.total_alerts > 0 or baseline_alerts):
        try:
            admin = settings.TELEGRAM_ADMIN
            if admin:
                for part in split_long_message(text):
                    await send_telegram_notify_async(admin, part)
                telegram_sent = True
                # 标记本批 baseline 告警已通知
                from sqlalchemy import update

                await db.execute(
                    update(AdDataHealthAlert)
                    .where(
                        AdDataHealthAlert.batch_id == batch_id,
                        AdDataHealthAlert.notified == False,  # noqa: E712
                    )
                    .values(notified=True)
                )
        except Exception as exc:
            logger.warning("健康巡检 Telegram 发送失败: %s", exc)

    return {
        "today": today.isoformat(),
        "batch_id": batch_id,
        "pool_size": report.pool_size,
        "watch_force_products": len(force_ids),
        "watch_window_status": watch_window_status,
        "report_alerts": report.total_alerts,
        "baseline_drop_alerts": len(baseline_alerts),
        "persisted_scan_alerts": persisted,
        "today_gap_suppressed": today_gap_suppressed,
        "today_gap_suppressed_count": suppressed_today_gap_count,
        "today_gap_alert_after_hour": TODAY_GAP_ALERT_AFTER_HOUR,
        "telegram_sent": telegram_sent,
        "summary_text": text,
    }
