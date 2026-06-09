"""
Postback 转化列表归因信息收集模块。

功能说明：
- 为转化列表展示批量收集 offer / publisher / advertiser 等 ID 集合
- 转化行上已有完整快照字段时跳过 Click 表查询，减少 N+1
- 从 gid 解析可能的 publisher_id，供名称解析等下游逻辑使用

在系统中的位置：
- 被 ``conversion_service``、转化列表 API 调用

注意事项：
1. 优先读快照列，仅缺失字段时才批量查 clicks
2. gid 解析规则与 Tracklink 生成约定保持一致
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import Click, PostbackConversion

logger = logging.getLogger(__name__)


def _needs_click_lookup(conv: PostbackConversion) -> bool:
    """有 click_id 但快照列（offer/publisher/advertiser/click_time）未齐时需查 Click 表。"""
    if not conv.click_id:
        return False
    return not (
        conv.offer_id
        and conv.publisher_id
        and conv.advertiser_id
        and conv.click_time
    )


async def load_clicks_map(
    db: AsyncSession,
    click_ids: Iterable[str],
) -> Dict[str, Dict[str, Any]]:
    """
    批量加载 Click 表归因字段。

    Args:
        db: 异步数据库会话。
        click_ids: 待查询的 click_id 集合（会去重、忽略空值）。

    Returns:
        click_id -> {offer_id, publisher_id, advertiser_id, click_time} 映射。
        查询失败时记录 debug 日志并返回空 dict，不阻断列表接口。
    """
    ids = list({cid for cid in click_ids if cid})
    if not ids:
        return {}
    clicks_map: Dict[str, Dict[str, Any]] = {}
    try:
        clicks_query = select(
            Click.click_id,
            Click.offer_id,
            Click.publisher_id,
            Click.advertiser_id,
            Click.click_time,
        ).where(Click.click_id.in_(ids))
        clicks_result = await db.execute(clicks_query)
        for row in clicks_result.all():
            clicks_map[row.click_id] = {
                "offer_id": row.offer_id,
                "publisher_id": row.publisher_id,
                "advertiser_id": row.advertiser_id,
                "click_time": row.click_time,
            }
    except Exception as e:
        logger.debug("无法从 Click 表加载数据: %s", e)
    return clicks_map


async def collect_attribution_ids(
    db: AsyncSession,
    conversions: List[PostbackConversion],
) -> Tuple[Set[int], Set[int], Set[int], Set[int], Dict[str, Dict[str, Any]]]:
    """
    从转化列表汇总归因相关 ID，并按需批量加载 Click 快照。

    流程：先扫描转化行快照与 gid → 收集需补查的 click_id →
    load_clicks_map 后合并 Click 中的 ID 到各集合。

    Args:
        db: 异步数据库会话。
        conversions: 当前页或批次的 PostbackConversion 列表。

    Returns:
        (offer_ids, publisher_ids, advertiser_ids, gid_publisher_ids, clicks_map)。
        clicks_map 仅包含本次补查到的 click 行；快照已齐的转化不在 map 中。
    """
    offer_ids: Set[int] = set()
    publisher_ids: Set[int] = set()
    advertiser_ids: Set[int] = set()
    gid_publisher_ids: Set[int] = set()
    click_ids_for_lookup: Set[str] = set()

    for conv in conversions:
        if conv.offer_id:
            offer_ids.add(conv.offer_id)
        if conv.publisher_id:
            publisher_ids.add(conv.publisher_id)
        if conv.advertiser_id:
            advertiser_ids.add(conv.advertiser_id)
        if _needs_click_lookup(conv):
            click_ids_for_lookup.add(conv.click_id)
        if conv.gid:
            try:
                gid_publisher_ids.add(int(conv.gid))
            except (ValueError, TypeError):
                pass

    clicks_map = await load_clicks_map(db, click_ids_for_lookup)
    # 将 Click 表补全的 ID 并入集合，供批量查名称等
    for info in clicks_map.values():
        if info.get("offer_id"):
            offer_ids.add(info["offer_id"])
        if info.get("publisher_id"):
            publisher_ids.add(info["publisher_id"])
        if info.get("advertiser_id"):
            advertiser_ids.add(info["advertiser_id"])

    return offer_ids, publisher_ids, advertiser_ids, gid_publisher_ids, clicks_map
