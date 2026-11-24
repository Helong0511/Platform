"""短链接热点缓存失效事件登记；与短链接变更共用数据库事务。"""
from __future__ import annotations

import re
import secrets
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import get_app_now_naive
from app.models.models import ShortLinkCacheInvalidationOutbox


SECOND_PASS_DELAY_SECONDS = 1
DEFAULT_MAX_ATTEMPTS = 12
_SHORT_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


async def enqueue_short_link_cache_invalidation(
    db: AsyncSession,
    short_code: str,
    *,
    second_pass_delay_seconds: int = SECOND_PASS_DELAY_SECONDS,
) -> None:
    """在调用方事务内登记立即清理与延迟复查；本函数绝不提交事务。

    仅接受短码，不接受任意 Redis key 或 glob，避免形成任意键删除能力。
    """
    if not isinstance(short_code, str) or not _SHORT_CODE_PATTERN.fullmatch(short_code):
        raise ValueError("short_code must contain 1-20 ASCII letters, digits, '_' or '-'")
    if (
        isinstance(second_pass_delay_seconds, bool)
        or not isinstance(second_pass_delay_seconds, int)
        or second_pass_delay_seconds < 1
        or second_pass_delay_seconds > 300
    ):
        raise ValueError("second_pass_delay_seconds must be between 1 and 300")

    now = get_app_now_naive()
    group_key = secrets.token_hex(32)
    events = []
    for phase, run_at in (
        ("first", now),
        ("second", now + timedelta(seconds=second_pass_delay_seconds)),
    ):
        events.append(
            ShortLinkCacheInvalidationOutbox(
                event_key=secrets.token_hex(32),
                group_key=group_key,
                short_code=short_code,
                phase=phase,
                status="pending",
                attempt_count=0,
                max_attempts=DEFAULT_MAX_ATTEMPTS,
                run_at=run_at,
            )
        )
    db.add_all(events)
    await db.flush()
