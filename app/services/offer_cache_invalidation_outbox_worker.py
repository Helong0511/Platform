"""Offer 热点缓存失效 Outbox Worker。

仅删除固定格式的 offer:cache:{id} 精确键，不接受任意 Redis pattern。
Redis 不可用或租约失效时不得确认成功；删除操作可安全重复执行。
"""
from __future__ import annotations

import logging
import os
import secrets
import socket

from sqlalchemy import exists, or_, select, update
from sqlalchemy.orm import aliased

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis_client
from app.core.utils import get_app_now_sql_expression
from app.models.models import OfferCacheInvalidationOutbox


logger = logging.getLogger(__name__)
OFFER_CACHE_INVALIDATION_LEASE_SECONDS = 300
OFFER_CACHE_INVALIDATION_BATCH_SIZE = 10
OFFER_CACHE_INVALIDATION_MAX_BACKOFF_SECONDS = 3600
OFFER_CACHE_KEY_PREFIX = "offer:cache:"


async def process_offer_cache_invalidation_outbox(
    *,
    batch_size: int = OFFER_CACHE_INVALIDATION_BATCH_SIZE,
) -> dict[str, int]:
    """认领并处理到期任务；多 Worker 使用行锁、租约和随机 fencing token。"""
    if batch_size < 1 or batch_size > 500:
        raise ValueError("batch_size must be between 1 and 500")

    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    claimed: list[tuple[int, str, int, int, int]] = []

    async with AsyncSessionLocal() as db:
        # 最后一次执行后进程崩溃，租约过期时必须收敛为 terminal failed。
        # 第二阶段必须等第一阶段已完成（success/failed），且只能在后续调度轮次认领，
        # 避免同一轮把两个阶段连续执行，失去延迟复查的意义。
        await db.execute(
            update(OfferCacheInvalidationOutbox)
            .where(
                OfferCacheInvalidationOutbox.status == "processing",
                OfferCacheInvalidationOutbox.lease_until <= get_app_now_sql_expression(),
                OfferCacheInvalidationOutbox.attempt_count >= OfferCacheInvalidationOutbox.max_attempts,
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
            update(OfferCacheInvalidationOutbox)
            .where(
                OfferCacheInvalidationOutbox.status == "pending",
                OfferCacheInvalidationOutbox.attempt_count >= OfferCacheInvalidationOutbox.max_attempts,
            )
            .values(
                status="failed",
                completed_at=get_app_now_sql_expression(),
                last_error_type="retry_budget_exhausted",
            )
        )

        first_pass = aliased(OfferCacheInvalidationOutbox)
        first_pass_finished = exists(
            select(1).where(
                first_pass.offer_id == OfferCacheInvalidationOutbox.offer_id,
                first_pass.phase == "first",
                first_pass.status.in_(("success", "failed")),
            )
        )
        pending_due = (
            (OfferCacheInvalidationOutbox.status == "pending")
            & (OfferCacheInvalidationOutbox.run_at <= get_app_now_sql_expression())
            & (
                (OfferCacheInvalidationOutbox.phase == "first")
                | (
                    (OfferCacheInvalidationOutbox.phase == "second")
                    & first_pass_finished
                )
            )
        )
        expired_lease = (
            (OfferCacheInvalidationOutbox.status == "processing")
            & (OfferCacheInvalidationOutbox.lease_until <= get_app_now_sql_expression())
        )
        rows = (
            await db.execute(
                select(OfferCacheInvalidationOutbox)
                .where(
                    or_(pending_due, expired_lease),
                    OfferCacheInvalidationOutbox.attempt_count
                    < OfferCacheInvalidationOutbox.max_attempts,
                )
                .order_by(OfferCacheInvalidationOutbox.id.asc())
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
                OFFER_CACHE_INVALIDATION_LEASE_SECONDS
            )
            claimed.append(
                (
                    int(row.id),
                    token,
                    int(row.offer_id),
                    int(row.attempt_count),
                    int(row.max_attempts),
                )
            )
        await db.commit()

    stats = {
        "claimed": len(claimed),
        "success": 0,
        "retryable": 0,
        "failed": 0,
        "lease_lost": 0,
    }

    for event_id, token, offer_id, attempt, max_attempts in claimed:
        try:
            # 校验当前租约后才触碰 Redis；旧 Worker 不能越过新 Worker 的 fencing token。
            async with AsyncSessionLocal() as db:
                owned = await db.scalar(
                    select(OfferCacheInvalidationOutbox.id).where(
                        OfferCacheInvalidationOutbox.id == event_id,
                        OfferCacheInvalidationOutbox.status == "processing",
                        OfferCacheInvalidationOutbox.lease_token == token,
                        OfferCacheInvalidationOutbox.lease_until
                        > get_app_now_sql_expression(),
                    )
                )
            if owned is None:
                stats["lease_lost"] += 1
                continue

            redis = await get_redis_client()
            if redis is None:
                raise RuntimeError("redis_unavailable")

            # 只删除该 Offer 的单一热点键；不使用 KEYS/SCAN/全库清理。
            await redis.delete(f"{OFFER_CACHE_KEY_PREFIX}{offer_id}")

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    update(OfferCacheInvalidationOutbox)
                    .where(
                        OfferCacheInvalidationOutbox.id == event_id,
                        OfferCacheInvalidationOutbox.status == "processing",
                        OfferCacheInvalidationOutbox.lease_token == token,
                        OfferCacheInvalidationOutbox.lease_until
                        > get_app_now_sql_expression(),
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
            backoff = min(
                5 * (2 ** min(attempt - 1, 10)),
                OFFER_CACHE_INVALIDATION_MAX_BACKOFF_SECONDS,
            )
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    update(OfferCacheInvalidationOutbox)
                    .where(
                        OfferCacheInvalidationOutbox.id == event_id,
                        OfferCacheInvalidationOutbox.status == "processing",
                        OfferCacheInvalidationOutbox.lease_token == token,
                        OfferCacheInvalidationOutbox.lease_until
                        > get_app_now_sql_expression(),
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
                "Offer cache invalidation failed: event_id=%s offer_id=%s "
                "error_type=%s terminal=%s",
                event_id,
                offer_id,
                type(exc).__name__,
                terminal,
            )

    return stats
