"""
Cap Reservation 崩溃恢复服务。

处理租约到期的 PREPARED / RESERVED，以及退避后可重试的 NEEDS_RECONCILIATION 记录；正式转化存在则保留计数，
确认未提交且 token PRESENT 才允许按原始 Redis key/token 原子回滚。
ABSENT / UNKNOWN 不执行 DECR，转入 NEEDS_RECONCILIATION。
"""
import logging
import uuid
from datetime import timedelta

from sqlalchemy import and_, func, or_, select

from app.core.cap.redis_counter import RedisCapManager
from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.cap_reservation import CapReservation
from app.models.models import PostbackConversion
from app.services.cap_reservation_ledger import CapReservationLedger

logger = logging.getLogger(__name__)

RECOVERY_LEASE_SECONDS = 300
RECOVERY_BATCH_SIZE = 100
RECONCILIATION_RETRY_SECONDS = 300


async def recover_cap_reservations(
    *,
    batch_size: int = RECOVERY_BATCH_SIZE,
) -> dict:
    """批量恢复到期账本；多 worker 通过 MySQL 行锁 + lease 避免重复处理。"""
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size 必须在 1 到 1000 之间")

    now = get_app_now_naive()
    rows = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CapReservation)
            .where(
                or_(
                    and_(
                        CapReservation.state.in_(("PREPARED", "RESERVED")),
                        or_(
                            CapReservation.lease_owner.is_(None),
                            CapReservation.lease_expires_at.is_(None),
                            CapReservation.lease_expires_at <= now,
                        ),
                    ),
                    and_(
                        CapReservation.state == "NEEDS_RECONCILIATION",
                        CapReservation.updated_at <= now - timedelta(
                            seconds=RECONCILIATION_RETRY_SECONDS
                        ),
                        or_(
                            CapReservation.lease_owner.is_(None),
                            CapReservation.lease_expires_at.is_(None),
                            CapReservation.lease_expires_at <= now,
                        ),
                    ),
                    and_(
                        CapReservation.state == "COMMITTED",
                        CapReservation.redis_token_cleaned.is_(False),
                        or_(
                            CapReservation.lease_owner.is_(None),
                            CapReservation.lease_expires_at.is_(None),
                            CapReservation.lease_expires_at <= now,
                        ),
                    ),
                )
            )
            .order_by(CapReservation.prepared_at.asc(), CapReservation.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.lease_owner = uuid.uuid4().hex
            row.lease_expires_at = now + timedelta(seconds=RECOVERY_LEASE_SECONDS)
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = now
        await session.commit()

    stats = {
        "claimed": len(rows),
        "committed": 0,
        "rolled_back": 0,
        "needs_reconciliation": 0,
        "tokens_cleaned": 0,
        "cleanup_pending": 0,
        "lease_lost": 0,
        "failed": 0,
    }

    for row in rows:
        owner = row.lease_owner
        try:
            # 批量认领时所有行共用同一租约截止时间；逐条处理前续租。
            # 若等待期间另一 Worker 已接管，则 owner 校验失败，本 Worker 必须跳过。
            lease_renewed = await CapReservationLedger.renew_recovery_lease(
                row.reservation_key,
                owner,
                lease_seconds=RECOVERY_LEASE_SECONDS,
            )
            if not lease_renewed:
                stats["lease_lost"] += 1
                continue

            if row.state == "COMMITTED":
                await RedisCapManager.delete_reservation_token(row.redis_token_key)
                await CapReservationLedger.mark_token_cleaned(
                    row.reservation_key, owner
                )
                stats["tokens_cleaned"] += 1
                continue

            async with AsyncSessionLocal() as session:
                event_id = await session.scalar(
                    select(PostbackConversion.id)
                    .where(
                        PostbackConversion.platform == row.platform,
                        PostbackConversion.conversion_id == row.conversion_id,
                        PostbackConversion.event_name == row.event_name,
                    )
                    .limit(1)
                )

            if event_id is not None:
                token_cleaned = await CapReservationLedger.finalize(
                    row.reservation_key, "COMMITTED", lease_owner=owner
                )
                stats["committed"] += 1
                if token_cleaned:
                    stats["tokens_cleaned"] += 1
                else:
                    stats["cleanup_pending"] += 1
                continue

            # 即使 redis_reserved=false 也必须检查 token：进程可能在 Redis Lua 成功后、
            # 写入 RESERVED 状态前被杀死。token PRESENT 时必须撤销该孤儿预留。
            token_state = await RedisCapManager.get_reservation_token_state(
                row.redis_counter_key, row.redis_token_key
            )
            if token_state == "PRESENT":
                daily_scope_expired = (
                    row.cap_kind == "daily"
                    and row.business_date is not None
                    and (get_app_now_naive().date() - row.business_date).days >= 2
                )
                if daily_scope_expired:
                    counter_exists = await RedisCapManager.counter_key_exists(
                        row.redis_counter_key
                    )
                    if counter_exists is False:
                        # Daily counter 已按 48h TTL 自然过期；token 本身无 TTL，
                        # 因此必须显式清理孤儿 token，不能尝试对不存在的 counter 执行 DECR。
                        await RedisCapManager.delete_reservation_token(row.redis_token_key)
                        await CapReservationLedger.finalize(
                            row.reservation_key, "ROLLED_BACK", lease_owner=owner
                        )
                        stats["rolled_back"] += 1
                        continue

                rollback_result = await RedisCapManager.rollback_reservation_keys(
                    row.redis_counter_key, row.redis_token_key
                )
                if rollback_result >= 0:
                    await CapReservationLedger.finalize(
                        row.reservation_key, "ROLLED_BACK", lease_owner=owner
                    )
                    stats["rolled_back"] += 1
                    continue
                reason = f"Redis token PRESENT but atomic rollback returned {rollback_result}"
            elif token_state == "ABSENT":
                # token 缺失不能单独证明没有发生过 INCR：Redis allkeys-* 淘汰策略、
                # 人工删除或部分数据丢失都可能只丢 token 而保留 counter。
                # 只有 counter key 也明确不存在时，才可确认当前 Redis 中没有需要撤销的计数。
                counter_exists = await RedisCapManager.counter_key_exists(
                    row.redis_counter_key
                )
                if counter_exists is False:
                    await CapReservationLedger.finalize(
                        row.reservation_key, "ROLLED_BACK", lease_owner=owner
                    )
                    stats["rolled_back"] += 1
                    continue
                reason = (
                    "Redis token ABSENT while counter still exists or its existence is UNKNOWN; "
                    "cannot distinguish no reservation, completed rollback, or token eviction"
                )
            else:
                daily_scope_expired = (
                    row.cap_kind == "daily"
                    and row.business_date is not None
                    and (get_app_now_naive().date() - row.business_date).days >= 2
                )
                counter_exists = (
                    await RedisCapManager.counter_key_exists(row.redis_counter_key)
                    if daily_scope_expired else None
                )
                if daily_scope_expired and counter_exists is False:
                    # Daily 业务日已结束且 48h counter key 已自然过期；清理孤儿 token 即可，
                    # 不对不存在的历史计数器执行 DECR。
                    await RedisCapManager.delete_reservation_token(row.redis_token_key)
                    await CapReservationLedger.finalize(
                        row.reservation_key, "ROLLED_BACK", lease_owner=owner
                    )
                    stats["rolled_back"] += 1
                    continue
                reason = "Redis token state UNKNOWN; Redis unavailable or counter state missing"

            await CapReservationLedger.mark_needs_reconciliation(
                row.reservation_key, reason, lease_owner=owner
            )
            stats["needs_reconciliation"] += 1
        except Exception as exc:
            stats["failed"] += 1
            logger.error(
                "Cap Reservation 恢复失败：reservation_key=%s",
                row.reservation_key,
                exc_info=True,
            )
            # COMMITTED token 清理失败不改变业务终态；保留/等待租约到期后重试清理。
            if row.state != "COMMITTED":
                try:
                    await CapReservationLedger.mark_needs_reconciliation(
                        row.reservation_key, str(exc), lease_owner=owner
                    )
                    stats["needs_reconciliation"] += 1
                except Exception:
                    logger.critical(
                        "Cap Reservation 恢复失败且无法保存对账状态：%s",
                        row.reservation_key,
                        exc_info=True,
                    )

    logger.info("Cap Reservation 恢复任务完成：%s", stats)
    return stats



async def get_cap_reservation_recovery_status() -> dict:
    """读取恢复积压、人工对账数量和最老待处理年龄，供调度任务告警。"""
    now = get_app_now_naive()
    async with AsyncSessionLocal() as session:
        grouped = await session.execute(
            select(CapReservation.state, func.count(CapReservation.id))
            .where(
                CapReservation.state.in_(
                    ("PREPARED", "RESERVED", "NEEDS_RECONCILIATION")
                )
            )
            .group_by(CapReservation.state)
        )
        counts = {state: int(count) for state, count in grouped.all()}
        oldest_pending = await session.scalar(
            select(func.min(CapReservation.prepared_at)).where(
                CapReservation.state.in_(("PREPARED", "RESERVED"))
            )
        )
        cleanup_pending = await session.scalar(
            select(func.count(CapReservation.id)).where(
                CapReservation.state == "COMMITTED",
                CapReservation.redis_token_cleaned.is_(False),
            )
        )

    oldest_age_seconds = (
        max(0, int((now - oldest_pending).total_seconds()))
        if oldest_pending is not None else 0
    )
    return {
        "pending_prepared": counts.get("PREPARED", 0),
        "pending_reserved": counts.get("RESERVED", 0),
        "needs_reconciliation": counts.get("NEEDS_RECONCILIATION", 0),
        "committed_token_cleanup_pending": int(cleanup_pending or 0),
        "oldest_pending_seconds": oldest_age_seconds,
    }
