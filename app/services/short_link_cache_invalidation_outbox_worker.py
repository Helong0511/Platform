"""短链接热点缓存失效 Outbox Worker。

只删除固定前缀 + 已校验短码的精确 Redis key。Redis 不可用或租约丢失时
不得确认成功；通过两阶段清理覆盖并发请求在首次失效后回填的旧缓存。
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import socket

from sqlalchemy import exists, or_, select, update
from sqlalchemy.orm import aliased

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis_client
from app.core.utils import get_app_now_sql_expression
from app.models.models import ShortLinkCacheInvalidationOutbox


logger = logging.getLogger(__name__)
SHORT_LINK_CACHE_INVALIDATION_LEASE_SECONDS = 300
SHORT_LINK_CACHE_INVALIDATION_BATCH_SIZE = 20
SHORT_LINK_CACHE_INVALIDATION_MAX_BACKOFF_SECONDS = 3600
SHORT_LINK_CACHE_KEY_PREFIX = "short_link:"
_SHORT_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


async def process_short_link_cache_invalidation_outbox(
    *,
    batch_size: int = SHORT_LINK_CACHE_INVALIDATION_BATCH_SIZE,
) -> dict[str, int]:
    """认领并处理到期任务；多 Worker 使用行锁、租约和随机 fencing token。"""
    if batch_size < 1 or batch_size > 500:
        raise ValueError("batch_size must be between 1 and 500")

    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    claimed: list[tuple[int, str, str, int, int]] = []

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ShortLinkCacheInvalidationOutbox)
            .where(
                ShortLinkCacheInvalidationOutbox.status == "processing",
                ShortLinkCacheInvalidationOutbox.lease_until <= get_app_now_sql_expression(),
                ShortLinkCacheInvalidationOutbox.attempt_count >= ShortLinkCacheInvalidationOutbox.max_attempts,
            )
            .values(
                status="failed",
                completed_at=get_app_now_sql_expression(),
                locked_by=None,
                lease_token=None,
                lease_until=None,
                last_error_type="lease_expired_after_max_attempts",
            )
        )
        await db.execute(
            update(ShortLinkCacheInvalidationOutbox)
            .where(
                ShortLinkCacheInvalidationOutbox.status == "pending",
                ShortLinkCacheInvalidationOutbox.attempt_count >= ShortLinkCacheInvalidationOutbox.max_attempts,
            )
            .values(
                status="failed",
                completed_at=get_app_now_sql_expression(),
                last_error_type="retry_budget_exhausted",
            )
        )

        first_pass = aliased(ShortLinkCacheInvalidationOutbox)
        first_pass_finished = exists(
            select(1).where(
                first_pass.group_key == ShortLinkCacheInvalidationOutbox.group_key,
                first_pass.phase == "first",
                first_pass.status.in_(("success", "failed")),
            )
        )
        pending_due = (
            (ShortLinkCacheInvalidationOutbox.status == "pending")
            & (ShortLinkCacheInvalidationOutbox.run_at <= get_app_now_sql_expression())
            & (
                (ShortLinkCacheInvalidationOutbox.phase == "first")
                | (
                    (ShortLinkCacheInvalidationOutbox.phase == "second")
                    & first_pass_finished
                )
            )
        )
        expired_lease = (
            (ShortLinkCacheInvalidationOutbox.status == "processing")
            & (ShortLinkCacheInvalidationOutbox.lease_until <= get_app_now_sql_expression())
        )
        rows = (
            await db.execute(
                select(ShortLinkCacheInvalidationOutbox)
                .where(
                    or_(pending_due, expired_lease),
                    ShortLinkCacheInvalidationOutbox.attempt_count
                    < ShortLinkCacheInvalidationOutbox.max_attempts,
                )
                .order_by(ShortLinkCacheInvalidationOutbox.id.asc())
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()

        for row in rows:
            token = secrets.token_hex(16)
            row.status = "processing"
            row.attempt_count = int(row.attempt_count or 0) + 1
            row.locked_by = worker_id
            row.lease_token = token
            row.lease_until = get_app_now_sql_expression(
                SHORT_LINK_CACHE_INVALIDATION_LEASE_SECONDS
            )
            claimed.append(
                (
                    int(row.id),
                    token,
                    str(row.short_code),
                    int(row.attempt_count),
                    int(row.max_attempts),
                )
            )
        await db.commit()

    stats = {"claimed": len(claimed), "success": 0, "retryable": 0, "failed": 0, "lease_lost": 0}

    for event_id, token, short_code, attempt, max_attempts in claimed:
        try:
            async with AsyncSessionLocal() as db:
                owned = await db.scalar(
                    select(ShortLinkCacheInvalidationOutbox.id).where(
                        ShortLinkCacheInvalidationOutbox.id == event_id,
                        ShortLinkCacheInvalidationOutbox.status == "processing",
                        ShortLinkCacheInvalidationOutbox.lease_token == token,
                        ShortLinkCacheInvalidationOutbox.lease_until > get_app_now_sql_expression(),
                    )
                )
            if owned is None:
                stats["lease_lost"] += 1
                continue

            if not _SHORT_CODE_PATTERN.fullmatch(short_code):
                raise ValueError("invalid_short_code_in_outbox")

            redis = await get_redis_client()
            if redis is None:
                raise RuntimeError("redis_unavailable")

            # 只删除一个短码对应的精确键；DEL 返回 0 也属于幂等成功。
            await redis.delete(f"{SHORT_LINK_CACHE_KEY_PREFIX}{short_code}")

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    update(ShortLinkCacheInvalidationOutbox)
                    .where(
                        ShortLinkCacheInvalidationOutbox.id == event_id,
                        ShortLinkCacheInvalidationOutbox.status == "processing",
                        ShortLinkCacheInvalidationOutbox.lease_token == token,
                        ShortLinkCacheInvalidationOutbox.lease_until > get_app_now_sql_expression(),
                    )
                    .values(
                        status="success",
                        completed_at=get_app_now_sql_expression(),
                        locked_by=None,
                        lease_token=None,
                        lease_until=None,
                        last_error_type=None,
                    )
                )
                await db.commit()
            if (result.rowcount or 0) == 1:
                stats["success"] += 1
            else:
                stats["lease_lost"] += 1
        except Exception as exc:
            terminal = attempt >= max_attempts
            backoff = min(5 * (2 ** min(attempt - 1, 10)), SHORT_LINK_CACHE_INVALIDATION_MAX_BACKOFF_SECONDS)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    update(ShortLinkCacheInvalidationOutbox)
                    .where(
                        ShortLinkCacheInvalidationOutbox.id == event_id,
                        ShortLinkCacheInvalidationOutbox.status == "processing",
                        ShortLinkCacheInvalidationOutbox.lease_token == token,
                        ShortLinkCacheInvalidationOutbox.lease_until > get_app_now_sql_expression(),
                    )
                    .values(
                        status="failed" if terminal else "pending",
                        run_at=get_app_now_sql_expression(backoff),
                        locked_by=None,
                        lease_token=None,
                        lease_until=None,
                        last_error_type=type(exc).__name__[:128],
                        completed_at=get_app_now_sql_expression() if terminal else None,
                    )
                )
                await db.commit()
            if (result.rowcount or 0) == 1:
                stats["failed" if terminal else "retryable"] += 1
            else:
                stats["lease_lost"] += 1
            logger.warning(
                "Short-link cache invalidation failed: event_id=%s short_code=%s error_type=%s terminal=%s",
                event_id,
                short_code,
                type(exc).__name__,
                terminal,
            )

    return stats
