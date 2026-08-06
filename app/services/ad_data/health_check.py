"""
广告数据健康巡检（缺数 / 断档 / 今日未入库 / 日环比跌幅）。

按「天 × 产品」汇总后判定；收益口径为结算收益 ``revenue_after_deduct``。
供探针脚本与后续定时任务复用。eCPM 不参与本巡检。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Mapping, Optional, Sequence, Union

# 「昨有今无」在此小时（含）之前不落库、不进 Telegram，避免凌晨巡检刷屏。
# 业务时区以调用方传入的 now 为准（一般为 get_app_now()）。
TODAY_GAP_ALERT_AFTER_HOUR = 12


def _coerce_date(value: Any) -> date:
    """归一化为 date。必须先判 datetime：datetime 是 date 的子类。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def should_alert_today_gap(
    now: Optional[Union[datetime, time, int]] = None,
    *,
    after_hour: int = TODAY_GAP_ALERT_AFTER_HOUR,
) -> bool:
    """
    是否允许发出「昨有今无」告警。

    - now 为 datetime：取 .hour
    - now 为 time：取 .hour
    - now 为 int：视为小时 0–23
    - now 为 None：视为允许（由调用方决定是否传入当前时间）
    """
    if now is None:
        return True
    if isinstance(now, int):
        hour = now
    elif isinstance(now, datetime):
        hour = now.hour
    elif isinstance(now, time):
        hour = now.hour
    else:
        return True
    return hour >= after_hour



@dataclass(frozen=True)
class AdDataHealthConfig:
    """巡检参数（可用环境变量/CLI 覆盖）。"""

    lookback_days: int = 7
    active_days: int = 3
    streak_days: int = 3
    drop_ratio: float = 0.02
    revenue_floor: float = 1.0


@dataclass(frozen=True)
class ProductDayAgg:
    """单产品单日聚合。"""

    row_count: int = 0
    revenue_after: float = 0.0


@dataclass
class MissingItem:
    product_id: int
    product_name: str
    check_date: date
    days_with_data_in_lookback: int
    last_data_date: Optional[date]
    streak_before_check: int = 0
    is_streak_break: bool = False


@dataclass
class TodayGapItem:
    """昨天有数据、今天尚未入库。"""

    product_id: int
    product_name: str
    yesterday: date
    today: date
    yesterday_rows: int
    yesterday_revenue: float


@dataclass
class DropItem:
    product_id: int
    product_name: str
    yesterday: date
    day_before: date
    revenue_yesterday: float
    revenue_day_before: float
    drop_ratio: float


@dataclass
class BackfillDropItem:
    """倒扣巡查：今日重拉历史日上游，与库内结算收益对比。"""

    product_id: int
    product_name: str
    check_date: date
    revenue_db: float
    revenue_upstream: float
    drop_ratio: float
    source_label: str = "ZhiSuo"


@dataclass
class AdDataHealthReport:
    today: date
    yesterday: date
    day_before: date
    lookback_start: date
    pool_size: int
    config: AdDataHealthConfig
    streak_breaks: list[MissingItem] = field(default_factory=list)
    missing_yesterday: list[MissingItem] = field(default_factory=list)
    today_gaps: list[TodayGapItem] = field(default_factory=list)
    revenue_drops: list[DropItem] = field(default_factory=list)
    backfill_drops: list[BackfillDropItem] = field(default_factory=list)
    backfill_date: Optional[date] = None
    backfill_note: str = ""

    @property
    def total_alerts(self) -> int:
        return (
            len(self.streak_breaks)
            + len(self.missing_yesterday)
            + len(self.today_gaps)
            + len(self.revenue_drops)
            + len(self.backfill_drops)
        )


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _daterange(start: date, end: date) -> list[date]:
    """含首尾的连续日期列表。"""
    if end < start:
        return []
    days: list[date] = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def build_daily_map(
    rows: Sequence[Mapping[str, Any]],
) -> dict[int, dict[date, ProductDayAgg]]:
    """
    将查询行转为 product_id -> {date -> agg}。

    每行需含: product_id, data_date(或 date), row_count, revenue_after
    """
    out: dict[int, dict[date, ProductDayAgg]] = {}
    for row in rows:
        pid = int(row["product_id"])
        day = _coerce_date(row.get("data_date", row.get("date")))
        agg = ProductDayAgg(
            row_count=int(row.get("row_count") or 0),
            revenue_after=_as_float(
                row.get("revenue_after", row.get("revenue_before"))
            ),
        )
        out.setdefault(pid, {})[day] = agg
    return out


def select_monitoring_pool(
    *,
    product_ids: Sequence[int],
    daily_map: Mapping[int, Mapping[date, ProductDayAgg]],
    lookback_start: date,
    lookback_end: date,
    active_days: int,
    force_product_ids: Optional[Sequence[int]] = None,
) -> set[int]:
    """
    正常跑产品池：lookback 窗口内「有数据的天数」>= active_days。

    lookback_end 一般为昨天（不含今天，避免半日数据影响入池）。
    force_product_ids：重点关注产品，无视活跃天数强制入池。
    """
    pool: set[int] = set()
    window = set(_daterange(lookback_start, lookback_end))
    for pid in product_ids:
        days = daily_map.get(pid) or {}
        hit = sum(1 for d, agg in days.items() if d in window and agg.row_count > 0)
        if hit >= active_days:
            pool.add(pid)
    if force_product_ids:
        pool.update(int(pid) for pid in force_product_ids if pid is not None)
    return pool


def _streak_ending_at(
    days: Mapping[date, ProductDayAgg],
    *,
    end_exclusive: date,
) -> int:
    """从 end_exclusive 前一天往回数，连续有数据的天数。"""
    streak = 0
    cur = end_exclusive - timedelta(days=1)
    while True:
        agg = days.get(cur)
        if not agg or agg.row_count <= 0:
            break
        streak += 1
        cur -= timedelta(days=1)
    return streak


def _last_data_date(
    days: Mapping[date, ProductDayAgg],
    *,
    on_or_before: date,
) -> Optional[date]:
    candidates = [d for d, agg in days.items() if d <= on_or_before and agg.row_count > 0]
    return max(candidates) if candidates else None


def detect_ad_data_health(
    *,
    today: date,
    product_names: Mapping[int, str],
    daily_map: Mapping[int, Mapping[date, ProductDayAgg]],
    config: Optional[AdDataHealthConfig] = None,
    force_product_ids: Optional[Sequence[int]] = None,
) -> AdDataHealthReport:
    """
    执行四类检测：

    1. 连续有数后断档（昨天无数据 + 此前连续 streak_days 有数）
    2. 昨天缺数（入监控池且昨天无行；已在断档列表的不再重复进缺数列表）
    3. 昨天有数、今天尚未入库
    4. 昨天 vs 前天 结算收益跌幅 >= drop_ratio（两天都有数据，且前天收益 >= floor）

    force_product_ids：重点关注产品强制纳入监控池。
    """
    cfg = config or AdDataHealthConfig()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    lookback_start = yesterday - timedelta(days=cfg.lookback_days - 1)

    product_ids = sorted(set(product_names.keys()) | set(daily_map.keys()))
    if force_product_ids:
        product_ids = sorted(set(product_ids) | {int(p) for p in force_product_ids})
    pool = select_monitoring_pool(
        product_ids=product_ids,
        daily_map=daily_map,
        lookback_start=lookback_start,
        lookback_end=yesterday,
        active_days=cfg.active_days,
        force_product_ids=force_product_ids,
    )

    report = AdDataHealthReport(
        today=today,
        yesterday=yesterday,
        day_before=day_before,
        lookback_start=lookback_start,
        pool_size=len(pool),
        config=cfg,
    )

    lookback_dates = set(_daterange(lookback_start, yesterday))

    for pid in sorted(pool):
        name = product_names.get(pid) or f"产品#{pid}"
        days = daily_map.get(pid) or {}
        y_agg = days.get(yesterday)
        y_rows = y_agg.row_count if y_agg else 0
        days_in_lookback = sum(
            1 for d, agg in days.items() if d in lookback_dates and agg.row_count > 0
        )
        last_day = _last_data_date(days, on_or_before=yesterday)
        streak = _streak_ending_at(days, end_exclusive=yesterday)

        if y_rows <= 0:
            item = MissingItem(
                product_id=pid,
                product_name=name,
                check_date=yesterday,
                days_with_data_in_lookback=days_in_lookback,
                last_data_date=last_day,
                streak_before_check=streak,
                is_streak_break=streak >= cfg.streak_days,
            )
            if item.is_streak_break:
                report.streak_breaks.append(item)
            else:
                report.missing_yesterday.append(item)

    # 昨天有数、今天还没有：不限监控池（只要昨天有行）
    for pid, days in daily_map.items():
        y_agg = days.get(yesterday)
        if not y_agg or y_agg.row_count <= 0:
            continue
        t_agg = days.get(today)
        if t_agg and t_agg.row_count > 0:
            continue
        name = product_names.get(pid) or f"产品#{pid}"
        report.today_gaps.append(
            TodayGapItem(
                product_id=pid,
                product_name=name,
                yesterday=yesterday,
                today=today,
                yesterday_rows=y_agg.row_count,
                yesterday_revenue=y_agg.revenue_after,
            )
        )

    # 跌幅：昨天 vs 前天，两天都有数据（结算收益）
    for pid in sorted(set(daily_map.keys()) | pool):
        days = daily_map.get(pid) or {}
        y_agg = days.get(yesterday)
        b_agg = days.get(day_before)
        if not y_agg or y_agg.row_count <= 0:
            continue
        if not b_agg or b_agg.row_count <= 0:
            continue
        rev_y = y_agg.revenue_after
        rev_b = b_agg.revenue_after
        if rev_b < cfg.revenue_floor:
            continue
        if rev_y >= rev_b:
            continue
        drop = (rev_b - rev_y) / rev_b
        if drop + 1e-12 < cfg.drop_ratio:
            continue
        name = product_names.get(pid) or f"产品#{pid}"
        report.revenue_drops.append(
            DropItem(
                product_id=pid,
                product_name=name,
                yesterday=yesterday,
                day_before=day_before,
                revenue_yesterday=rev_y,
                revenue_day_before=rev_b,
                drop_ratio=drop,
            )
        )

    report.streak_breaks.sort(key=lambda x: (-x.streak_before_check, x.product_name))
    report.missing_yesterday.sort(
        key=lambda x: (-x.days_with_data_in_lookback, x.product_name)
    )
    report.today_gaps.sort(key=lambda x: (-x.yesterday_revenue, x.product_name))
    report.revenue_drops.sort(key=lambda x: (-x.drop_ratio, x.product_name))
    return report


def settle_upstream_revenue_by_product(
    rows: Sequence[Mapping[str, Any]],
    *,
    product_by_name: Mapping[str, tuple[int, float]],
    domain_key: str = "domain_name",
    revenue_key: str = "estimated_earnings",
) -> dict[int, float]:
    """
    将上游原始行按产品名汇总「结算收益」。

    product_by_name: 产品名 → (product_id, revenue_deduct_ratio)
    先按产品累加上游未扣收益，再套用产品扣减比例得到结算收益。
    """
    from collections import defaultdict

    from app.core.utils import apply_deduct_ratio

    raw_by_pid: dict[int, float] = defaultdict(float)
    deduct_by_pid: dict[int, float] = {}
    for row in rows:
        name = str(row.get(domain_key) or "").strip()
        if not name:
            continue
        info = product_by_name.get(name)
        if not info:
            continue
        pid, deduct = info
        raw_by_pid[pid] += _as_float(row.get(revenue_key))
        deduct_by_pid[pid] = float(deduct or 0)
    return {
        pid: apply_deduct_ratio(raw, deduct_by_pid.get(pid, 0.0))
        for pid, raw in raw_by_pid.items()
    }


def detect_backfill_drops(
    *,
    check_date: date,
    product_names: Mapping[int, str],
    db_settlement_by_product: Mapping[int, float],
    upstream_settlement_by_product: Mapping[int, float],
    drop_ratio: float = 0.02,
    revenue_floor: float = 1.0,
    source_label: str = "ZhiSuo",
) -> list[BackfillDropItem]:
    """
    倒扣巡查：库内历史日结算收益 vs 今日重拉上游结算收益。

    仅在库内结算收益 ≥ revenue_floor，且上游相对库内下降 ≥ drop_ratio 时告警。
    上游无该产品时按 0 计（视为收益消失）。
    """
    items: list[BackfillDropItem] = []
    for pid, db_rev in db_settlement_by_product.items():
        db_val = _as_float(db_rev)
        if db_val < revenue_floor:
            continue
        up_val = _as_float(upstream_settlement_by_product.get(pid, 0.0))
        if up_val >= db_val:
            continue
        drop = (db_val - up_val) / db_val
        if drop + 1e-12 < drop_ratio:
            continue
        items.append(
            BackfillDropItem(
                product_id=pid,
                product_name=product_names.get(pid) or f"产品#{pid}",
                check_date=check_date,
                revenue_db=db_val,
                revenue_upstream=up_val,
                drop_ratio=drop,
                source_label=source_label,
            )
        )
    items.sort(key=lambda x: (-x.drop_ratio, x.product_name))
    return items


def format_health_report_text(
    report: AdDataHealthReport,
    *,
    max_items_per_section: int = 80,
    baseline_alert_count: int = 0,
    today_gap_suppressed: bool = False,
    today_gap_suppress_hour: int = TODAY_GAP_ALERT_AFTER_HOUR,
) -> str:
    """生成可读巡检文案（控制台 / Telegram）。"""
    cfg = report.config
    scan_alerts = report.total_alerts
    combined_alerts = scan_alerts + max(0, int(baseline_alert_count or 0))
    lines: list[str] = [
        "📊 广告数据健康巡检",
        "",
        f"今日: {report.today.isoformat()}",
        f"检查缺数日(昨天): {report.yesterday.isoformat()}",
        f"跌幅对照(前天): {report.day_before.isoformat()}",
        f"监控池: {report.pool_size} 个产品"
        f"（最近 {cfg.lookback_days} 天内至少 {cfg.active_days} 天有数据）",
        f"规则: 连续≥{cfg.streak_days}天有数据后断档 | 结算收益跌幅≥{cfg.drop_ratio:.0%}"
        f"（前天结算收益≥{cfg.revenue_floor:g}）| 昨天有数据今天还没有"
        f"（{today_gap_suppress_hour}:00 前不报）"
        f" | 倒扣巡查（相对日标准：请求数与收益扣前）",
        f"告警合计: {combined_alerts}"
        + (
            f"（日级 {scan_alerts} + 倒扣 {baseline_alert_count}）"
            if baseline_alert_count
            else ""
        ),
        "",
    ]
    if today_gap_suppressed:
        lines.append(
            f"ℹ️ 「昨有今无」已跳过：当前早于 {today_gap_suppress_hour}:00"
            f"（避免凌晨误报；下午仍无大面积数据时再告警）"
        )
        lines.append("")


    def _section(title: str, count: int) -> None:
        lines.append(f"{title}（{count}）")
        if count == 0:
            lines.append("  （无）")
            lines.append("")

    _section("🚨 连续有数据后突然没有（断档）", len(report.streak_breaks))
    for item in report.streak_breaks[:max_items_per_section]:
        last = item.last_data_date.isoformat() if item.last_data_date else "-"
        lines.append(
            f"【{item.product_name}】连续 {item.streak_before_check} 天有数据"
            f" → {item.check_date.isoformat()} 没有数据（最近一次有数据：{last}）"
        )
    if len(report.streak_breaks) > max_items_per_section:
        lines.append(f"  … 另有 {len(report.streak_breaks) - max_items_per_section} 条省略")
    if report.streak_breaks:
        lines.append("")

    _section("⚠️ 昨天没有数据（监控池）", len(report.missing_yesterday))
    for item in report.missing_yesterday[:max_items_per_section]:
        last = item.last_data_date.isoformat() if item.last_data_date else "-"
        lines.append(
            f"【{item.product_name}】{item.check_date.isoformat()} 没有数据"
            f"（最近 {report.config.lookback_days} 天里有 {item.days_with_data_in_lookback} 天有数据，"
            f"最近一次有数据：{last}）"
        )
    if len(report.missing_yesterday) > max_items_per_section:
        lines.append(
            f"  … 另有 {len(report.missing_yesterday) - max_items_per_section} 条省略"
        )
    if report.missing_yesterday:
        lines.append("")

    _section("🕒 昨天有数据、今天还没有拉到", len(report.today_gaps))
    for item in report.today_gaps[:max_items_per_section]:
        lines.append(
            f"【{item.product_name}】{item.yesterday.isoformat()} "
            f"{item.yesterday_rows} 行 / 结算收益 {item.yesterday_revenue:.2f}"
            f" → {item.today.isoformat()} 还没有数据"
        )
    if len(report.today_gaps) > max_items_per_section:
        lines.append(f"  … 另有 {len(report.today_gaps) - max_items_per_section} 条省略")
    if report.today_gaps:
        lines.append("")

    _section(
        f"📉 日环比结算收益跌幅≥{cfg.drop_ratio:.0%}"
        f"（{report.yesterday.isoformat()} vs {report.day_before.isoformat()}）",
        len(report.revenue_drops),
    )
    for item in report.revenue_drops[:max_items_per_section]:
        lines.append(
            f"【{item.product_name}】"
            f"{item.revenue_day_before:.2f} → {item.revenue_yesterday:.2f}"
            f"（{item.drop_ratio:.1%}）"
        )
    if len(report.revenue_drops) > max_items_per_section:
        lines.append(f"  … 另有 {len(report.revenue_drops) - max_items_per_section} 条省略")
    if report.revenue_drops:
        lines.append("")

    backfill_day = report.backfill_date or report.day_before
    # 新倒扣：相对「日标准」；若仍有 backfill_drops 则展示旧 live 对比明细
    if report.backfill_drops:
        backfill_title = (
            f"🔄 倒扣巡查：今日重拉 {backfill_day.isoformat()} 与库内对比，"
            f"结算收益跌≥{cfg.drop_ratio:.0%}"
        )
        _section(backfill_title, len(report.backfill_drops))
        for item in report.backfill_drops[:max_items_per_section]:
            lines.append(
                f"【{item.product_name}】库内 {item.revenue_db:.2f}"
                f" → 上游现拉 {item.revenue_upstream:.2f}"
                f"（{item.drop_ratio:.1%}，{item.source_label}）"
            )
        if len(report.backfill_drops) > max_items_per_section:
            lines.append(
                f"  … 另有 {len(report.backfill_drops) - max_items_per_section} 条省略"
            )
        if report.backfill_note:
            lines.append(f"  说明: {report.backfill_note}")
        lines.append("")
    else:
        lines.append(
            f"🔄 倒扣巡查：相对日标准（{backfill_day.isoformat()}，"
            f"粒度=日期+产品+来源；对比请求数与收益扣前）"
        )
        if report.backfill_note:
            lines.append(f"  （{report.backfill_note}）")
        else:
            lines.append("  （无明细；详见告警表 baseline_drop）")
        lines.append("")

    if combined_alerts == 0:
        lines.append("✅ 巡检正常：无缺数/断档/今日未入库/跌幅/倒扣告警")
    else:
        if report.today_gaps:
            lines.append(
                f"ℹ️ 「今天还没有拉到」在 {today_gap_suppress_hour}:00 前通常不报；"
                "若下午仍大面积没有，优先排查拉数任务。"
            )
        lines.append("ℹ️ 倒扣巡查：相对已冻结日标准对比请求数与收益扣前；入库后也会抽查昨天/前天。")

    return "\n".join(lines).rstrip() + "\n"


def report_to_dict(report: AdDataHealthReport) -> dict[str, Any]:
    """便于探针 --json 输出。"""
    return {
        "today": report.today.isoformat(),
        "yesterday": report.yesterday.isoformat(),
        "day_before": report.day_before.isoformat(),
        "lookback_start": report.lookback_start.isoformat(),
        "pool_size": report.pool_size,
        "config": {
            "lookback_days": report.config.lookback_days,
            "active_days": report.config.active_days,
            "streak_days": report.config.streak_days,
            "drop_ratio": report.config.drop_ratio,
            "revenue_floor": report.config.revenue_floor,
        },
        "total_alerts": report.total_alerts,
        "streak_breaks": [
            {
                "product_id": x.product_id,
                "product_name": x.product_name,
                "check_date": x.check_date.isoformat(),
                "streak_before_check": x.streak_before_check,
                "last_data_date": x.last_data_date.isoformat() if x.last_data_date else None,
                "days_with_data_in_lookback": x.days_with_data_in_lookback,
            }
            for x in report.streak_breaks
        ],
        "missing_yesterday": [
            {
                "product_id": x.product_id,
                "product_name": x.product_name,
                "check_date": x.check_date.isoformat(),
                "last_data_date": x.last_data_date.isoformat() if x.last_data_date else None,
                "days_with_data_in_lookback": x.days_with_data_in_lookback,
                "streak_before_check": x.streak_before_check,
            }
            for x in report.missing_yesterday
        ],
        "today_gaps": [
            {
                "product_id": x.product_id,
                "product_name": x.product_name,
                "yesterday": x.yesterday.isoformat(),
                "today": x.today.isoformat(),
                "yesterday_rows": x.yesterday_rows,
                "yesterday_revenue": round(x.yesterday_revenue, 4),
            }
            for x in report.today_gaps
        ],
        "revenue_drops": [
            {
                "product_id": x.product_id,
                "product_name": x.product_name,
                "yesterday": x.yesterday.isoformat(),
                "day_before": x.day_before.isoformat(),
                "revenue_yesterday": round(x.revenue_yesterday, 4),
                "revenue_day_before": round(x.revenue_day_before, 4),
                "drop_ratio": round(x.drop_ratio, 6),
            }
            for x in report.revenue_drops
        ],
        "backfill_date": report.backfill_date.isoformat() if report.backfill_date else None,
        "backfill_note": report.backfill_note,
        "backfill_drops": [
            {
                "product_id": x.product_id,
                "product_name": x.product_name,
                "check_date": x.check_date.isoformat(),
                "revenue_db": round(x.revenue_db, 4),
                "revenue_upstream": round(x.revenue_upstream, 4),
                "drop_ratio": round(x.drop_ratio, 6),
                "source_label": x.source_label,
            }
            for x in report.backfill_drops
        ],
    }
