"""广告数据查询缓存失效 Outbox Worker。

Generation 是缓存正确性的边界；本 Worker 负责持久化清理旧键。
只有共享 Redis 明确确认成功时，任务才允许进入 success。
"""
from __future__ import annotations

import logging
import os
import socket
import secrets

from sqlalchemy import or_, select, update

from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_sql_expression
from app.models.models import CacheInvalidationOutbox
from app.services.ad_data.query_cache import AD_DATA_QUERY_CACHE_NS

logger = logging.getLogger(__name__)
CACHE_INVALIDATION_LEASE_SECONDS = 300
CACHE_INVALIDATION_BATCH_SIZE = 5
CACHE_INVALIDATION_MAX_BACKOFF_SECONDS = 3600


async def process_cache_invalidation_outbox(
    *,
    batch_size: int = CACHE_INVALIDATION_BATCH_SIZE,
) -> dict[str, int]:
    """认领并处理一批到期失效任务；可在多 Worker 环境并发执行。"""
    if batch_size < 1 or batch_size > 100:
        raise ValueError("batch_size must be between 1 and 100")

    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    claimed: list[tuple[int, str, int, int]] = []

    async with AsyncSessionLocal() as db:
        # 最后一次尝试后若 Worker 崩溃，租约到期时必须收敛为 failed，不能永久卡在 processing。
        await db.execute(
            update(CacheInvalidationOutbox)
            .where(
                CacheInvalidationOutbox.status == "processing",
                CacheInvalidationOutbox.lease_until <= get_app_now_sql_expression(),
                CacheInvalidationOutbox.attempt_count >= CacheInvalidationOutbox.max_attempts,
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
            update(CacheInvalidationOutbox)
            .where(
                CacheInvalidationOutbox.status == "pending",
                CacheInvalidationOutbox.attempt_count >= CacheInvalidationOutbox.max_attempts,
            )
            .values(
                status="failed",
                completed_at=get_app_now_sql_expression(),
                last_error_type="retry_budget_exhausted",
            )
        )
        rows = (
            await db.execute(
                select(CacheInvalidationOutbox)
                .where(
                    or_(
                        (
                            (CacheInvalidationOutbox.status == "pending")
                            & (CacheInvalidationOutbox.next_retry_time <= get_app_now_sql_expression())
                        ),
                        (
                            (CacheInvalidationOutbox.status == "processing")
                            & (CacheInvalidationOutbox.lease_until <= get_app_now_sql_expression())
                        ),
                    ),
                    CacheInvalidationOutbox.attempt_count < CacheInvalidationOutbox.max_attempts,
                )
                .order_by(CacheInvalidationOutbox.id.asc())
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
            row.lease_until = get_app_now_sql_expression(CACHE_INVALIDATION_LEASE_SECONDS)
            claimed.append((int(row.id), token, int(row.attempt_count), int(row.max_attempts)))
        await db.commit()

    stats = {"claimed": len(claimed), "success": 0, "retryable": 0, "failed": 0, "lease_lost": 0}
    for event_id, token, attempt, max_attempts in claimed:
        try:
            async with AsyncSessionLocal() as db:
                event = await db.scalar(
                    select(CacheInvalidationOutbox).where(
                        CacheInvalidationOutbox.id == event_id,
                        CacheInvalidationOutbox.status == "processing",
                        CacheInvalidationOutbox.lease_token == token,
                        CacheInvalidationOutbox.lease_until > get_app_now_sql_expression(),
                    )
                )
                if event is None:
                    stats["lease_lost"] += 1
                    continue
                namespace = event.namespace

            if namespace != AD_DATA_QUERY_CACHE_NS:
                raise ValueError("unsupported_cache_namespace")

            from app.core.infrastructure.cache_compat import invalidate_cache_checked

            result = await invalidate_cache_checked(f"{namespace}:")
            if not result.operation_succeeded or not result.shared_store_confirmed:
                raise RuntimeError(result.error_code or "shared_cache_invalidation_unconfirmed")

            async with AsyncSessionLocal() as db:
                updated = await db.execute(
                    update(CacheInvalidationOutbox)
                    .where(
                        CacheInvalidationOutbox.id == event_id,
                        CacheInvalidationOutbox.status == "processing",
                        CacheInvalidationOutbox.lease_token == token,
                        CacheInvalidationOutbox.lease_until > get_app_now_sql_expression(),
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
                if (updated.rowcount or 0) == 1:
                    stats["success"] += 1
                else:
                    stats["lease_lost"] += 1
        except Exception as exc:
            terminal = attempt >= max_attempts
            backoff = min(30 * (2 ** min(attempt - 1, 10)), CACHE_INVALIDATION_MAX_BACKOFF_SECONDS)
            async with AsyncSessionLocal() as db:
                updated = await db.execute(
                    update(CacheInvalidationOutbox)
                    .where(
                        CacheInvalidationOutbox.id == event_id,
                        CacheInvalidationOutbox.status == "processing",
                        CacheInvalidationOutbox.lease_token == token,
                        CacheInvalidationOutbox.lease_until > get_app_now_sql_expression(),
                    )
                    .values(
                        status="failed" if terminal else "pending",
                        next_retry_time=get_app_now_sql_expression(backoff),
                        locked_by=None,
                        lease_token=None,
                        lease_until=None,
                        last_error_type=type(exc).__name__[:128],
                        completed_at=get_app_now_sql_expression() if terminal else None,
                    )
                )
                await db.commit()
                if (updated.rowcount or 0) == 1:
                    stats["failed" if terminal else "retryable"] += 1
                else:
                    stats["lease_lost"] += 1
            logger.warning(
                "Cache invalidation Outbox processing failed: event_id=%s error_type=%s terminal=%s",
                event_id,
                type(exc).__name__,
                terminal,
            )

    return stats
