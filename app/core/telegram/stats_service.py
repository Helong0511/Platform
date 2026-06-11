"""
Telegram Bot 广告数据统计查询与消息格式化。

Bot 回调线程内创建独立 async 引擎并调用 AdDataSummaryQuery，
与 Web 端广告数据表格合计行口径一致；支持按产品分组展示。
"""
import asyncio
import html
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from app.core.telegram.stats_period import resolve_stats_date_range
from app.core.telegram_utils import format_telegram_message, split_long_message

logger = logging.getLogger(__name__)

STATS_MENU_CALLBACK = "stats_menu"

STATS_PERIOD_BUTTONS: List[List[Dict[str, str]]] = [
    [
        {"text": "📅 昨天", "callback_data": "stats_yesterday"},
        {"text": "📆 本周", "callback_data": "stats_this_week"},
    ],
    [
        {"text": "📋 上周", "callback_data": "stats_last_week"},
        {"text": "🗓 本月", "callback_data": "stats_this_month"},
    ],
]


def build_stats_menu_buttons(include_back: bool = False) -> List[List[Dict[str, str]]]:
    """构建统计周期选择按钮；结果页可附加返回菜单按钮。"""
    buttons = [row[:] for row in STATS_PERIOD_BUTTONS]
    if include_back:
        buttons.append([{"text": "◀️ 返回菜单", "callback_data": STATS_MENU_CALLBACK}])
    return buttons


def _fmt_count(value: Any) -> str:
    return f"{int(value or 0):,}"


def _fmt_pct(value: Any) -> str:
    return f"{float(value or 0):.2f}%"


def _fmt_money(value: Any, digits: int = 2) -> str:
    return f"${float(value or 0):.{digits}f}"


def _format_date_range_text(summary: Dict[str, Any]) -> str:
    date_range = summary.get("date_range") or {}
    start_date = date_range.get("start_date", "")
    end_date = date_range.get("end_date", "")
    if hasattr(start_date, "isoformat"):
        start_date = start_date.isoformat()
    if hasattr(end_date, "isoformat"):
        end_date = end_date.isoformat()
    return f"{start_date} ~ {end_date}"


def _build_metric_fields(summary: Dict[str, Any]) -> Dict[str, str]:
    """单条汇总（全量或单产品）的指标字段。"""
    fields = {
        "请求数": _fmt_count(summary.get("request_count")),
        "匹配数": _fmt_count(summary.get("match_count")),
        "覆盖率": _fmt_pct(summary.get("coverage_rate")),
        "展示数": _fmt_count(summary.get("display_count")),
        "展示率": _fmt_pct(summary.get("display_rate")),
        "点击数": _fmt_count(summary.get("click_count")),
        "点击率": _fmt_pct(summary.get("click_rate")),
        "可见率": _fmt_pct(summary.get("viewability_rate")),
        "CPC": _fmt_money(summary.get("cpc"), 4),
        "PageViews": _fmt_count(summary.get("pageviews")),
        "eCPM(扣)": _fmt_money(summary.get("ecpm_after_deduct"), 4),
        "收益(扣)": _fmt_money(summary.get("revenue_after_deduct"), 4),
    }
    if summary.get("ecpm_before_deduct") is not None:
        fields["eCPM"] = _fmt_money(summary.get("ecpm_before_deduct"), 4)
        fields["收益"] = _fmt_money(summary.get("revenue_before_deduct"), 4)
    return fields


def _format_product_block(product: Dict[str, Any], index: int) -> str:
    """单个产品的紧凑指标块。"""
    name = html.escape(str(product.get("product_name") or "未知产品"))
    product_id = product.get("product_id", "")
    fields = _build_metric_fields(product)

    lines = [f"\n<b>{index}. {name}</b> (ID: {product_id})"]
    line_groups = [
        ("请求数", "匹配数", "覆盖率"),
        ("展示数", "展示率", "点击数", "点击率"),
        ("可见率", "CPC", "PageViews"),
        ("eCPM(扣)", "收益(扣)", "eCPM", "收益"),
    ]
    for group in line_groups:
        parts = [f"{key} {fields[key]}" for key in group if key in fields]
        if parts:
            lines.append("   " + " | ".join(parts))
    return "\n".join(lines)


def format_stats_message(payload: Dict[str, Any], period_label: str) -> str:
    """
    将广告数据汇总格式化为 Telegram 消息。

    payload 含 total（全量）与 products（按产品列表）。
    """
    total = payload.get("total") or payload
    products = payload.get("products") or []
    date_text = _format_date_range_text(total)

    message = format_telegram_message(
        title=f"{period_label}广告数据统计",
        fields=_build_metric_fields(total),
        footer=f"📅 统计区间: {date_text}",
        message_type="stats",
    )

    if products:
        message += f"\n\n<b>📦 分产品统计（共 {len(products)} 个）</b>"
        for idx, product in enumerate(products, 1):
            message += _format_product_block(product, idx)
    else:
        message += "\n\n<i>该周期内暂无分产品数据</i>"

    return message


def format_stats_messages(payload: Dict[str, Any], period_label: str) -> List[str]:
    """格式化并按 Telegram 长度限制拆分为多条消息。"""
    return split_long_message(format_stats_message(payload, period_label))


async def _fetch_ad_data_summary_isolated(period_key: str) -> Dict[str, Any]:
    """在独立 async 引擎中调用 AdDataSummaryQuery（全量 + 分产品）。"""
    import app.core.database  # noqa: F401
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.scheduler_module.task_utils import get_admin_user
    from app.services.ad_data.queries.summary_query import AdDataSummaryQuery

    start_str, end_str, _ = resolve_stats_date_range(period_key)
    start_date = date.fromisoformat(start_str)
    end_date = date.fromisoformat(end_str)

    db_url = str(settings.SQLALCHEMY_DATABASE_URI)
    engine_kwargs: Dict[str, Any] = {
        "echo": False,
        "pool_pre_ping": True,
    }
    if not db_url.startswith("sqlite"):
        engine_kwargs.update({
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_size": 2,
            "max_overflow": 1,
            "connect_args": {"connect_timeout": 10},
        })

    engine = create_async_engine(db_url, **engine_kwargs)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    try:
        async with session_factory() as db:
            admin_user = await get_admin_user(db)
            if not admin_user:
                raise RuntimeError("未找到管理员账号，无法查询统计")

            query = AdDataSummaryQuery(db)
            total = await query.fetch(
                current_user=admin_user,
                start_date=start_date,
                end_date=end_date,
                skip_cache=True,
            )
            products = await query.fetch_by_product(
                current_user=admin_user,
                start_date=start_date,
                end_date=end_date,
            )
            return {"total": total, "products": products}
    finally:
        await engine.dispose()


def fetch_stats_sync(period_key: str) -> Optional[Dict[str, Any]]:
    """同步拉取统计：供 Telegram 回调线程调用。"""
    try:
        return asyncio.run(_fetch_ad_data_summary_isolated(period_key))
    except Exception as exc:
        logger.error(f"Telegram 统计查询失败: period={period_key}, error={exc}", exc_info=True)
        return None
