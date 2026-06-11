"""
Telegram Bot 转化统计查询与消息格式化。

在独立线程中通过异步会话调用 ConversionService，与 Web 端转化总览口径一致。
"""
import asyncio
import html
import logging
from typing import Any, Dict, List, Optional

from app.core.telegram.stats_period import resolve_stats_date_range
from app.core.telegram_utils import format_telegram_message, truncate_message

logger = logging.getLogger(__name__)

STATS_MENU_CALLBACK = "stats_menu"

# 内联键盘：四个统计周期 + 返回（统计结果页使用）
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
    将转化总览数据格式化为 Telegram 消息（纯文本，配合 HTML 发送时需转义特殊字符）。

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


async def _fetch_conversion_summary(period_key: str) -> Dict[str, Any]:
    """异步拉取管理员视角转化总览。"""
    from app.core.database import AsyncSessionLocal
    from app.scheduler_module.task_utils import get_admin_user
    from app.services.cpl.conversion_service import ConversionService

    start_date, end_date, _ = resolve_stats_date_range(period_key)

    async with AsyncSessionLocal() as db:
        admin_user = await get_admin_user(db)
        if not admin_user:
            raise RuntimeError("未找到管理员账号，无法查询统计")

        service = ConversionService(db)
        return await service.get_conversion_summary(
            current_user=admin_user,
            start_date=start_date,
            end_date=end_date,
        )


def fetch_stats_sync(period_key: str) -> Optional[Dict[str, Any]]:
    """
    同步封装：供 Telegram 回调线程调用。

    Returns:
        转化总览字典；失败时返回 None
    """
    try:
        return asyncio.run(_fetch_conversion_summary(period_key))
    except Exception as exc:
        logger.error(f"Telegram 统计查询失败: period={period_key}, error={exc}", exc_info=True)
        return None
