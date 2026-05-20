"""
Postback 转化列表归因信息收集（优先快照列，按需查 clicks）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import Click, PostbackConversion

logger = logging.getLogger(__name__)


def _needs_click_lookup(conv: PostbackConversion) -> bool:
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
    返回 (offer_ids, publisher_ids, advertiser_ids, gid_publisher_ids, clicks_map)。
    快照列已齐的转化不再查 clicks。
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
    for info in clicks_map.values():
        if info.get("offer_id"):
            offer_ids.add(info["offer_id"])
        if info.get("publisher_id"):
            publisher_ids.add(info["publisher_id"])
        if info.get("advertiser_id"):
            advertiser_ids.add(info["advertiser_id"])

    return offer_ids, publisher_ids, advertiser_ids, gid_publisher_ids, clicks_map
