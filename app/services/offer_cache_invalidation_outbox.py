"""Offer 热点缓存失效事件登记；事件与 Offer 业务变更共用事务。"""
from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import get_app_now_naive
from app.models.models import OfferCacheInvalidationOutbox


SECOND_PASS_DELAY_SECONDS = 1
DEFAULT_MAX_ATTEMPTS = 12


async def enqueue_offer_cache_invalidation(
    db: AsyncSession,
    offer_id: int,
    *,
    second_pass_delay_seconds: int = SECOND_PASS_DELAY_SECONDS,
) -> None:
    """在调用方事务内登记立即清理与延迟复查；本函数绝不提交事务。

    使用固定事件类型和 Offer 主键，不接受外部传入 Redis key 或 glob，
    避免把任意键删除能力暴露给业务输入。
    """
    if isinstance(offer_id, bool) or not isinstance(offer_id, int) or offer_id < 1:
        raise ValueError("offer_id must be a positive integer")
    if (
        isinstance(second_pass_delay_seconds, bool)
        or not isinstance(second_pass_delay_seconds, int)
        or second_pass_delay_seconds < 1
        or second_pass_delay_seconds > 300
    ):
        raise ValueError("second_pass_delay_seconds must be between 1 and 300")

    now = get_app_now_naive()
    events = []
    for phase, run_at in (
        ("first", now),
        ("second", now + timedelta(seconds=second_pass_delay_seconds)),
    ):
        events.append(
            OfferCacheInvalidationOutbox(
                event_key=secrets.token_hex(32),
                offer_id=offer_id,
                phase=phase,
                status="pending",
                attempt_count=0,
                max_attempts=DEFAULT_MAX_ATTEMPTS,
                run_at=run_at,
            )
        )
    db.add_all(events)
    await db.flush()
