"""
Cap 管理逻辑
用于检查 Cap 限制和自动下线
"""
import logging
import uuid
from typing import Optional, Tuple
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from sqlalchemy import update
from app.models.models import OfferCap, Offer, PostbackConversion

logger = logging.getLogger(__name__)

from app.core.cap.redis_counter import RedisCapManager, get_daily_cap_key, get_total_cap_key
from app.core.config import settings
from app.core.redis_client import get_redis_client
from app.core.utils import get_app_now_naive
from app.services.cap_reservation_ledger import CapReservationLedger


async def check_cap(
    db: AsyncSession,
    offer_id: int,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None
) -> Tuple[bool, Optional[str]]:
    """
    检查 Cap 限制
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        publisher_id: 渠道ID（可选）
        advertiser_id: 广告主ID（可选）
        
    Returns:
        (是否允许, 拒绝原因)
    """
    try:
        # 查询所有相关的 Cap 配置
        query = select(OfferCap).where(
            and_(
                OfferCap.offer_id == offer_id,
                OfferCap.is_active == True
            )
        )
        
        # 如果指定了渠道，优先匹配渠道特定的 Cap
        if publisher_id:
            query = query.where(
                or_(
                    OfferCap.publisher_id == publisher_id,
                    OfferCap.publisher_id.is_(None)  # 也检查所有渠道的 Cap
                )
            )
        else:
            query = query.where(OfferCap.publisher_id.is_(None))
        
        # 如果指定了广告主，检查 advertiser_offer 类型的 Cap
        if advertiser_id:
            query = query.where(
                or_(
                    OfferCap.cap_type == 'offer',
                    and_(
                        OfferCap.cap_type == 'advertiser_offer',
                        OfferCap.advertiser_id == advertiser_id
                    )
                )
            )
        else:
            query = query.where(OfferCap.cap_type == 'offer')
        
        result = await db.execute(query)
        caps = result.scalars().all()
        
        if not caps:
            # 没有 Cap 配置，允许通过
            return True, None
        
        # 检查每个 Cap 配置
        now = get_app_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        for cap in caps:
            # 检查每日 Cap
            if cap.daily_cap:
                # ====== 优化：使用 Redis 获取当前计数 ======
                redis = await get_redis_client()
                actual_count = 0
                
                if redis:
                    # 尝试从 Redis 读取
                    # 读取 Redis key 前刷新业务时间，并同步刷新日期边界；
                    # 避免首次取时与实际 key 日期跨午夜后，拿昨日 DB 计数阻止今日请求。
                    now = get_app_now_naive()
                    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    redis_key = get_daily_cap_key(cap.offer_id, now, cap.publisher_id)
                    redis_val = await redis.get(redis_key)
                    
                    db_daily_count = (
                        int(cap.current_daily_count or 0)
                        if cap.cap_start_date
                        and cap.cap_start_date.date() == today_start.date()
                        else 0
                    )
                    if redis_val is not None:
                        # 与原子预留路径一致，不能让 Redis 回退低于 DB 已确认计数。
                        actual_count = max(int(redis_val), db_daily_count)
                    else:
                        # 缺失 key 可能是 Redis 重启/淘汰或在途 reservation；
                        # 这里只做只读预检查，不得 SET/SETNX 重建，最终由 Lua 原子预留初始化。
                        actual_count = db_daily_count
                else:
                    # Redis 不可用，降级到 DB 缓存字段 (不再执行实时 COUNT)
                    if cap.cap_start_date and cap.cap_start_date.date() == today_start.date():
                        actual_count = cap.current_daily_count
                    else:
                        actual_count = 0
                
                if actual_count >= cap.daily_cap:
                    return False, f"已达到每日Cap限制: {cap.daily_cap} (当前: {actual_count})"
            
            # 检查总 Cap（与 increment 一致：优先读 Redis total key）
            if cap.total_cap:
                actual_total_count = cap.current_total_count
                redis = await get_redis_client()
                if redis:
                    try:
                        total_key = get_total_cap_key(cap.offer_id, cap.publisher_id)
                        redis_val = await redis.get(total_key)
                        if redis_val is not None:
                            # Redis 计数不得低于 DB 已确认值；实际预留仍由 Lua 原子判定。
                            actual_total_count = max(
                                int(redis_val),
                                int(cap.current_total_count or 0),
                            )
                        # key 缺失时只读使用 DB 值，不在预检查阶段重建 Redis key。
                    except Exception as e:
                        logger.warning(f"读取 Redis 总Cap失败，回退 DB 字段: {e}")
                if actual_total_count >= cap.total_cap:
                     return False, f"已达到总Cap限制: {cap.total_cap} (当前: {actual_total_count})"
        
        return True, None
    except Exception as e:
        logger.error(f"检查Cap失败: {str(e)}", exc_info=True)
        if settings.CAP_FAIL_OPEN:
            logger.warning("Cap 检查异常，fail-open 放行")
            return True, None
        return False, "cap_check_error"


async def _rollback_reserved_redis(reserved: list[tuple]) -> None:
    """按 token 回滚 Redis，并同步结束对应账本；未知状态保留待对账。"""
    failures = []
    for reservation in reserved:
        kind, oid, pid = reservation[:3]
        reservation_date = reservation[3] if len(reservation) > 3 else None
        reservation_id = reservation[4] if len(reservation) > 4 else None
        ledger_key = reservation[5] if len(reservation) > 5 else None
        lease_owner = reservation[6] if len(reservation) > 6 else None
        redis_reserved = reservation[7] if len(reservation) > 7 else True
        try:
            if redis_reserved:
                if kind == "daily":
                    result = await RedisCapManager.decrement_daily(
                        oid, pid, reservation_date=reservation_date, reservation_id=reservation_id
                    )
                elif kind == "total":
                    result = await RedisCapManager.decrement_total(
                        oid, pid, reservation_id=reservation_id
                    )
                else:
                    raise RuntimeError(f"unknown kind={kind}, offer_id={oid}")
                if result < 0:
                    raise RuntimeError(f"Redis rollback unresolved: kind={kind}, offer_id={oid}, token={reservation_id}")
            if ledger_key:
                await CapReservationLedger.finalize(ledger_key, "ROLLED_BACK", lease_owner=lease_owner)
        except Exception as exc:
            if ledger_key:
                try:
                    await CapReservationLedger.mark_needs_reconciliation(
                        ledger_key, str(exc), lease_owner=lease_owner
                    )
                except Exception:
                    logger.critical("无法更新 Cap Reservation 对账状态：%s", ledger_key, exc_info=True)
            failures.append(f"kind={kind}, offer_id={oid}, token={reservation_id}, error={exc}")
            logger.error("Cap reservation rollback failed; continue with remaining tokens", exc_info=True)
    if failures:
        raise RuntimeError("Cap reservation rollback incomplete: " + "; ".join(failures))


async def _prepare_cap_ledger_reservation(
    reservation_context: Optional[dict], *, offer_id: int,
    publisher_id: Optional[int], cap_kind: str, business_date,
):
    """无事件上下文时兼容旧调用；Postback 路径必须先独立提交 PREPARED。"""
    if not reservation_context:
        return uuid.uuid4().hex, None, None
    row, claimed, lease_owner = await CapReservationLedger.prepare_and_claim(
        platform=reservation_context["platform"],
        conversion_id=reservation_context["conversion_id"],
        event_name=reservation_context.get("event_name"),
        offer_id=offer_id, publisher_id=publisher_id,
        cap_kind=cap_kind, business_date=business_date,
    )
    if not claimed:
        raise RuntimeError(
            f"Cap Reservation 已由其他请求处理或需要对账：key={row.reservation_key}, state={row.state}"
        )
    return row.reservation_key, row.reservation_key, lease_owner


async def _mark_ledger_redis_reserved(
    ledger_key: Optional[str], lease_owner: Optional[str], *,
    kind: str, offer_id: int, publisher_id: Optional[int],
    reservation_date: Optional[datetime], reservation_id: str,
) -> None:
    """Redis 已成功 INCR 后确认账本；状态写入失败则按同一 token 补偿。"""
    if not ledger_key:
        return
    try:
        await CapReservationLedger.mark_reserved(ledger_key, lease_owner)
    except Exception as exc:
        try:
            if kind == "daily":
                rolled_back = await RedisCapManager.decrement_daily(
                    offer_id, publisher_id, reservation_date=reservation_date,
                    reservation_id=reservation_id,
                )
            else:
                rolled_back = await RedisCapManager.decrement_total(
                    offer_id, publisher_id, reservation_id=reservation_id
                )
            if rolled_back >= 0:
                await CapReservationLedger.finalize(
                    ledger_key, "ROLLED_BACK", lease_owner=lease_owner
                )
            else:
                await CapReservationLedger.mark_needs_reconciliation(
                    ledger_key, f"RESERVED 标记失败且 Redis 补偿未知：{exc}",
                    lease_owner=lease_owner,
                )
        except Exception as rollback_error:
            await CapReservationLedger.mark_needs_reconciliation(
                ledger_key, f"RESERVED 标记失败：{exc}; Redis 补偿失败：{rollback_error}",
                lease_owner=lease_owner,
            )
        raise


async def _refresh_offer_caps(db: AsyncSession, caps: list) -> None:
    """丢弃会话中未提交的 Cap ORM 脏写，避免超限/失败路径误 commit。"""
    for cap in caps:
        try:
            await db.refresh(cap)
        except Exception as e:
            logger.debug("刷新 OfferCap 失败（可忽略）: id=%s err=%s", getattr(cap, "id", None), e)


async def increment_cap_count(
    db: AsyncSession,
    offer_id: int,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    *,
    session_flush: bool = True,
    include_reservations: bool = False,
    reservation_context: Optional[dict] = None,
) -> Tuple[bool, str] | Tuple[bool, str, list[tuple]]:
    """
    增加 Cap 计数 (线程/进程安全版本)
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        publisher_id: 渠道ID（可选）
        advertiser_id: 广告主ID（可选）
        
    Returns:
        (是否预留成功, 状态)：
        - (True, "cap_ok")
        - (False, "cap_exceeded") 真超限
        - (False, "cap_check_error") 基础设施失败（调用方应拒绝入库并允许重试）
    """
    caps = []
    reserved: list[tuple] = []

    def _result(ok: bool, status: str):
        if include_reservations:
            return ok, status, list(reserved)
        return ok, status

    try:
        # 1. 查询所有相关的 Cap 配置，使用 with_for_update() 进行行级锁定
        query = select(OfferCap).where(
            and_(
                OfferCap.offer_id == offer_id,
                OfferCap.is_active == True
            )
        ).order_by(OfferCap.id.asc()).with_for_update()
        
        if publisher_id:
            query = query.where(
                or_(
                    OfferCap.publisher_id == publisher_id,
                    OfferCap.publisher_id.is_(None)
                )
            )
        else:
            query = query.where(OfferCap.publisher_id.is_(None))
        
        if advertiser_id:
            query = query.where(
                or_(
                    OfferCap.cap_type == 'offer',
                    and_(
                        OfferCap.cap_type == 'advertiser_offer',
                        OfferCap.advertiser_id == advertiser_id
                    )
                )
            )
        else:
            query = query.where(OfferCap.cap_type == 'offer')
        
        result = await db.execute(query)
        caps = list(result.scalars().all())
        
        now = get_app_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 同一 Redis key 可能对应 Offer 全局 Cap 与广告主-Offer Cap。
        # 它们约束的是同一 Offer/渠道转化集合，必须共享一个计数；逐条预留会把单次转化重复计数。
        daily_groups: dict[tuple[int, Optional[int]], list] = {}
        total_groups: dict[tuple[int, Optional[int]], list] = {}
        for cap in caps:
            group_key = (cap.offer_id, cap.publisher_id)
            if cap.daily_cap:
                daily_groups.setdefault(group_key, []).append(cap)
            if cap.total_cap:
                total_groups.setdefault(group_key, []).append(cap)

        # 2. 每个 Daily Redis key 只原子预留一次；多个约束取最严格上限。
        for (group_offer_id, group_publisher_id), group_caps in daily_groups.items():
            db_daily_counts = [
                int(cap.current_daily_count or 0)
                if cap.cap_start_date
                and cap.cap_start_date.date() == today_start.date()
                else 0
                for cap in group_caps
            ]
            redis_init_val = max(db_daily_counts, default=0)
            effective_limit = min(int(cap.daily_cap) for cap in group_caps)
            reservation_id, ledger_key, lease_owner = await _prepare_cap_ledger_reservation(
                reservation_context, offer_id=group_offer_id,
                publisher_id=group_publisher_id, cap_kind="daily",
                business_date=today_start.date(),
            )
            try:
                passed = await RedisCapManager.check_and_increment_daily(
                    group_offer_id, effective_limit, group_publisher_id,
                    initial_value=redis_init_val, reservation_id=reservation_id,
                    reservation_date=now,
                )
            except Exception as e:
                if ledger_key:
                    await CapReservationLedger.mark_needs_reconciliation(
                        ledger_key, str(e), lease_owner=lease_owner
                    )
                logger.error("Cap 日计数预留/补偿状态不确定，拒绝本次转化：%s", e, exc_info=True)
                await _rollback_reserved_redis(reserved)
                reserved.clear()
                await _refresh_offer_caps(db, caps)
                return _result(False, "cap_check_error")

            if passed is False:
                if ledger_key:
                    await CapReservationLedger.finalize(
                        ledger_key, "ROLLED_BACK", lease_owner=lease_owner
                    )
                logger.warning(
                    "每日Cap超限: offer=%s publisher=%s limit=%s current=%s cap_ids=%s",
                    group_offer_id, group_publisher_id, effective_limit,
                    redis_init_val, [cap.id for cap in group_caps],
                )
                await _rollback_reserved_redis(reserved)
                reserved.clear()
                await _refresh_offer_caps(db, caps)
                return _result(False, "cap_exceeded")

            redis_reserved = passed is True
            if redis_reserved:
                await _mark_ledger_redis_reserved(
                    ledger_key, lease_owner, kind="daily", offer_id=group_offer_id,
                    publisher_id=group_publisher_id, reservation_date=today_start,
                    reservation_id=reservation_id,
                )
            reserved.append((
                "daily", group_offer_id, group_publisher_id, today_start,
                reservation_id, ledger_key, lease_owner, redis_reserved,
            ))

            # 多个配置共享同一实际计数，保持 DB 快照一致；fail-open 时也只增加一次。
            for cap in group_caps:
                cap.cap_start_date = today_start
                cap.current_daily_count = redis_init_val + 1

        # 3. 每个 Total Redis key 只原子预留一次；多个约束取最严格上限。
        for (group_offer_id, group_publisher_id), group_caps in total_groups.items():
            redis_init_val = max(
                (int(cap.current_total_count or 0) for cap in group_caps),
                default=0,
            )
            effective_limit = min(int(cap.total_cap) for cap in group_caps)
            reservation_id, ledger_key, lease_owner = await _prepare_cap_ledger_reservation(
                reservation_context, offer_id=group_offer_id,
                publisher_id=group_publisher_id, cap_kind="total",
                business_date=None,
            )
            try:
                passed = await RedisCapManager.check_and_increment_total(
                    group_offer_id, effective_limit, group_publisher_id,
                    initial_value=redis_init_val, reservation_id=reservation_id,
                )
            except Exception as e:
                if ledger_key:
                    await CapReservationLedger.mark_needs_reconciliation(
                        ledger_key, str(e), lease_owner=lease_owner
                    )
                logger.error("Cap 总计数预留/补偿状态不确定，拒绝本次转化：%s", e, exc_info=True)
                await _rollback_reserved_redis(reserved)
                reserved.clear()
                await _refresh_offer_caps(db, caps)
                return _result(False, "cap_check_error")

            if passed is False:
                if ledger_key:
                    await CapReservationLedger.finalize(
                        ledger_key, "ROLLED_BACK", lease_owner=lease_owner
                    )
                logger.warning(
                    "总Cap超限: offer=%s publisher=%s limit=%s current=%s cap_ids=%s",
                    group_offer_id, group_publisher_id, effective_limit,
                    redis_init_val, [cap.id for cap in group_caps],
                )
                await _rollback_reserved_redis(reserved)
                reserved.clear()
                await _refresh_offer_caps(db, caps)
                return _result(False, "cap_exceeded")

            redis_reserved = passed is True
            if redis_reserved:
                await _mark_ledger_redis_reserved(
                    ledger_key, lease_owner, kind="total", offer_id=group_offer_id,
                    publisher_id=group_publisher_id, reservation_date=None,
                    reservation_id=reservation_id,
                )
            reserved.append((
                "total", group_offer_id, group_publisher_id, None,
                reservation_id, ledger_key, lease_owner, redis_reserved,
            ))

            for cap in group_caps:
                if not cap.cap_start_date:
                    cap.cap_start_date = now
                cap.current_total_count = redis_init_val + 1

        # 由调用方控制外层事务时可选跳过 flush，与转化入库同一 commit
        if session_flush:
            await db.flush()
        return _result(True, "cap_ok")
        
    except Exception as e:
        logger.error(f"增加Cap计数失败: {str(e)}", exc_info=True)
        try:
            await _rollback_reserved_redis(reserved)
            reserved.clear()
        except Exception:
            pass
        if caps:
            await _refresh_offer_caps(db, caps)
        raise


async def rollback_cap_redis_counts(
    db: AsyncSession,
    offer_id: int,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    *,
    reservations: Optional[list[tuple]] = None,
) -> None:
    """
    仅按当前请求的 reservation token 回退 Redis Cap。

    旧版无 token 的全量 DECR 会误减并发请求的计数，故不再执行。
    未提供 reservation 时保留计数并记录告警，交由对账任务处理。
    """
    if not offer_id:
        return
    if not reservations:
        logger.critical(
            "拒绝执行无 token 的 Cap Redis 回滚，避免误减并发请求名额："
            "offer_id=%s publisher_id=%s advertiser_id=%s",
            offer_id,
            publisher_id,
            advertiser_id,
        )
        return
    await _rollback_reserved_redis(reservations)


async def reset_daily_caps(db: AsyncSession) -> None:
    """
    重置已跨日的每日 Cap DB 计数。

    使用行锁与 Postback 的 Cap 预留串行化，避免午夜并发请求被重置覆盖。
    不删除 Redis 今日 key：定时任务可能在当天已有流量后才运行，删除今日 key
    会丢失已经发生的 reservation。历史日期 key 由 TTL 自然回收。
    """
    try:
        # 先锁定全部有效的每日 Cap，再读取业务日期。
        # 不能在等待行锁前计算 today_start：任务可能在锁等待期间跨过午夜，
        # 用旧日期筛选/重置会漏掉刚跨日的记录，或写入过期的日期标记。
        query = (
            select(OfferCap)
            .where(
                and_(
                    OfferCap.is_active == True,
                    OfferCap.daily_cap > 0,
                )
            )
            .order_by(OfferCap.id.asc())
            .with_for_update()
        )
        result = await db.execute(query)
        locked_caps = result.scalars().all()

        # 必须在获得所有目标行锁之后读取业务日期，确保与转化预留串行化时使用当前日期。
        now = get_app_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        caps_to_reset = [
            cap for cap in locked_caps
            if cap.cap_start_date is None or cap.cap_start_date < today_start
        ]

        # 不通过 bulk UPDATE 绕开 ORM 行锁状态，也不清理今天可能已经创建的 Redis key。
        for cap in caps_to_reset:
            cap.current_daily_count = 0
            cap.cap_start_date = today_start

        await db.commit()
        logger.info(
            "每日 Cap 跨日重置完成：更新 %s 条记录；保留 Redis 今日计数 key",
            len(caps_to_reset),
        )
    except Exception as e:
        logger.error("每日 Cap 跨日重置失败: %s", e, exc_info=True)
        await db.rollback()
        raise
