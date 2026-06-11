"""
Telegram Bot 转化统计查询与消息格式化。

Bot 回调线程内使用 pymysql 同步查询，避免与主进程 asyncio 事件循环冲突。
"""
import html
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased

from app.core.telegram.stats_period import resolve_stats_date_range
from app.core.telegram.sync_db import get_sync_session_factory
from app.core.telegram_utils import format_telegram_message, truncate_message
from app.core.utils import parse_date_to_app_timezone
from app.models.models import Click, Offer, PostbackConversion, Publisher

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


def format_stats_message(summary: Dict[str, Any], period_label: str) -> str:
    """
    将转化总览数据格式化为 Telegram 消息。

    包含汇总指标与按 Offer×渠道 的前 8 条分类明细。
    """
    start_date = summary.get("start_date", "")
    end_date = summary.get("end_date", "")
    cr = summary.get("cr") or 0

    fields = {
        "总点击": summary.get("total_clicks", 0),
        "总转化": summary.get("total_conversions", 0),
        "转化率": f"{cr:.2f}%",
        "总 PO": f"${float(summary.get('total_po') or 0):.2f}",
        "扣后 PO": f"${float(summary.get('total_po_after_discount') or 0):.2f}",
        "总利润": f"${float(summary.get('total_profit') or 0):.2f}",
    }

    footer = f"📅 统计区间: {start_date} ~ {end_date}"

    message = format_telegram_message(
        title=f"{period_label}转化统计",
        fields=fields,
        footer=footer,
        message_type="stats",
    )

    stats_list = summary.get("stats_list") or []
    if stats_list:
        sorted_rows = sorted(
            stats_list,
            key=lambda row: row.get("conversion_count") or 0,
            reverse=True,
        )[:8]
        message += "\n\n<b>分类明细（Top 8）</b>\n"
        for idx, row in enumerate(sorted_rows, 1):
            offer_name = html.escape(str(row.get("offer_name") or "未知 Offer"))
            publisher_name = html.escape(str(row.get("publisher_name") or "未知渠道"))
            clicks = row.get("click_count") or 0
            conversions = row.get("conversion_count") or 0
            row_cr = row.get("cr") or 0
            message += (
                f"\n{idx}. {offer_name}\n"
                f"   渠道: {publisher_name}\n"
                f"   点击 {clicks} | 转化 {conversions} | CR {row_cr:.2f}%"
            )

    return truncate_message(message)


def _query_conversion_summary_sync(period_key: str) -> Dict[str, Any]:
    """
    同步查询管理员视角转化总览（口径与 Web 端 ConversionService 分组统计一致）。
    """
    start_date, end_date, _ = resolve_stats_date_range(period_key)
    start_datetime = parse_date_to_app_timezone(start_date, is_end_date=False)
    end_datetime = parse_date_to_app_timezone(end_date, is_end_date=False) + timedelta(days=1)

    click_conditions = [
        Click.click_time >= start_datetime,
        Click.click_time < end_datetime,
    ]
    conversion_conditions = [
        PostbackConversion.created_at >= start_datetime,
        PostbackConversion.created_at < end_datetime,
    ]

    SessionLocal = get_sync_session_factory()
    with SessionLocal() as db:
        total_clicks = db.execute(
            select(func.count(Click.id)).where(and_(*click_conditions))
        ).scalar() or 0

        click_groups = db.execute(
            select(
                Click.offer_id,
                Click.publisher_id,
                func.count(Click.id).label("click_count"),
            )
            .where(and_(*click_conditions))
            .group_by(Click.offer_id, Click.publisher_id)
        ).all()

        stats_dict: Dict[tuple, Dict[str, Any]] = {}
        offer_ids: set = set()
        publisher_ids: set = set()

        for offer_id_val, publisher_id_val, click_count_val in click_groups:
            if not offer_id_val:
                continue
            safe_publisher_id = publisher_id_val if publisher_id_val is not None else 0
            key = (offer_id_val, safe_publisher_id)
            stats_dict[key] = {
                "offer_id": offer_id_val,
                "publisher_id": safe_publisher_id,
                "click_count": click_count_val,
                "conversion_count": 0,
                "po": 0.0,
                "po_after_discount": 0.0,
            }
            offer_ids.add(offer_id_val)
            if safe_publisher_id:
                publisher_ids.add(safe_publisher_id)

        click_alias = aliased(Click)
        offer_alias = aliased(Offer)

        conversion_groups = db.execute(
            select(
                click_alias.offer_id.label("offer_id"),
                click_alias.publisher_id.label("publisher_id"),
                func.count(PostbackConversion.id).label("conversion_count"),
                func.sum(PostbackConversion.original_payout).label("total_po_original"),
                func.sum(PostbackConversion.payout).label("total_po_discounted"),
            )
            .join(click_alias, PostbackConversion.click_id == click_alias.click_id)
            .join(offer_alias, click_alias.offer_id == offer_alias.id)
            .where(
                and_(
                    *conversion_conditions,
                    click_alias.offer_id.isnot(None),
                    click_alias.publisher_id.isnot(None),
                )
            )
            .group_by(click_alias.offer_id, click_alias.publisher_id)
        ).all()

        total_conversions = 0
        total_po = 0.0
        total_po_after_discount = 0.0

        for row in conversion_groups:
            offer_id_val = row.offer_id
            pub_id_val = row.publisher_id
            conv_count = int(row.conversion_count or 0)
            po_original = float(row.total_po_original or 0)
            po_discounted = float(row.total_po_discounted or 0)

            key = (offer_id_val, pub_id_val)
            if key not in stats_dict:
                stats_dict[key] = {
                    "offer_id": offer_id_val,
                    "publisher_id": pub_id_val,
                    "click_count": 0,
                    "conversion_count": 0,
                    "po": 0.0,
                    "po_after_discount": 0.0,
                }

            stats_dict[key]["conversion_count"] += conv_count
            stats_dict[key]["po"] += po_original
            stats_dict[key]["po_after_discount"] += po_discounted

            total_conversions += conv_count
            total_po += po_original
            total_po_after_discount += po_discounted
            offer_ids.add(offer_id_val)
            publisher_ids.add(pub_id_val)

        offers_map = {}
        if offer_ids:
            for offer in db.execute(select(Offer).where(Offer.id.in_(offer_ids))).scalars():
                offers_map[offer.id] = offer

        publishers_map = {}
        if publisher_ids:
            for publisher in db.execute(
                select(Publisher).where(Publisher.id.in_(publisher_ids))
            ).scalars():
                publishers_map[publisher.id] = publisher

        stats_list = []
        for stat in stats_dict.values():
            offer = offers_map.get(stat["offer_id"])
            publisher = publishers_map.get(stat["publisher_id"]) if stat["publisher_id"] else None
            click_count = stat["click_count"]
            conversion_count = stat["conversion_count"]
            row_cr = (conversion_count / click_count * 100) if click_count > 0 else 0.0

            stats_list.append({
                "offer_id": stat["offer_id"],
                "offer_name": offer.offer_name if offer else "未关联 Offer",
                "publisher_id": stat["publisher_id"],
                "publisher_name": publisher.publisher_name if publisher else "未关联渠道",
                "click_count": click_count,
                "conversion_count": conversion_count,
                "cr": round(row_cr, 2),
                "po": stat["po"],
                "po_after_discount": round(stat["po_after_discount"], 2),
            })

        cr = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0.0
        total_profit = total_po - total_po_after_discount

        return {
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "cr": round(cr, 2),
            "total_po": total_po,
            "total_po_after_discount": total_po_after_discount,
            "total_profit": total_profit,
            "stats_list": stats_list,
            "start_date": start_date,
            "end_date": end_date,
        }


def fetch_stats_sync(period_key: str) -> Optional[Dict[str, Any]]:
    """
    同步拉取统计：供 Telegram 回调线程调用。

    Returns:
        转化总览字典；失败时返回 None
    """
    try:
        return _query_conversion_summary_sync(period_key)
    except Exception as exc:
        logger.error(f"Telegram 统计查询失败: period={period_key}, error={exc}", exc_info=True)
        return None
