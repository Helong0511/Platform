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
                    now = get_app_now_naive()
                    redis_key = get_daily_cap_key(cap.offer_id, now, cap.publisher_id)
                    redis_val = await redis.get(redis_key)
                    
                    if redis_val is not None:
                        actual_count = int(redis_val)
                    else:
                        # Redis 未命中（冷启动），从 DB 初始化
                        if cap.cap_start_date and cap.cap_start_date.date() == today_start.date():
                             actual_count = cap.current_daily_count
                        else:
                             actual_count = 0
                        
                        # SET NX：禁止覆盖并发路径已写入的计数
                        try:
                            await redis.set(
                                redis_key,
                                actual_count,
                                ex=48 * 3600,
                                nx=True,
                            )
                        except Exception as e:
                            logger.warning(f"Redis回写失败: {e}")
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
                            actual_total_count = int(redis_val)
                        else:
                            await redis.set(
                                total_key,
                                actual_total_count,
                                ex=30 * 24 * 3600,
                                nx=True,
                            )
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


async def _rollback_reserved_redis(
    reserved: list[tuple],
) -> None:
    for reservation in reserved:
        kind, oid, pid = reservation[:3]
        reservation_date = reservation[3] if len(reservation) > 3 else None
        reservation_id = reservation[4] if len(reservation) > 4 else None
        if kind == "daily":
            result = await RedisCapManager.decrement_daily(
                oid,
                pid,
                reservation_date=reservation_date,
                reservation_id=reservation_id,
            )
        else:
            result = await RedisCapManager.decrement_total(
                oid, pid, reservation_id=reservation_id
            )
        if result < 0:
            raise RuntimeError(
                f"Cap reservation rollback failed: kind={kind}, offer_id={oid}, token={reservation_id}"
            )


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
) -> Tuple[bool, str] | Tuple[bool, str, list[tuple[str, int, Optional[int], Optional[datetime]]]]:
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
        ).with_for_update()
        
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
        
        for cap in caps:
            # 2. 处理每日计数（Redis 先预留名额，成功后再更新 DB）
            if cap.daily_cap:
                is_new_day = (
                    not cap.cap_start_date
                    or cap.cap_start_date.date() < today_start.date()
                )
                # 先算 init，预留成功后再写 ORM，避免失败路径脏写
                redis_init_val = 0 if is_new_day else (cap.current_daily_count or 0)

                reservation_id = uuid.uuid4().hex
                try:
                    passed = await RedisCapManager.check_and_increment_daily(
                        cap.offer_id,
                        cap.daily_cap,
                        cap.publisher_id,
                        initial_value=redis_init_val,
                        reservation_id=reservation_id,
                    )
                except Exception as e:
                    logger.warning(f"Redis计数递增同步失败: {e}")
                    if settings.CAP_FAIL_OPEN:
                        # fail-open：不改 Redis/ORM 日计数，继续处理 total
                        logger.warning("Cap 日计数 Redis 失败，fail-open 跳过日计数")
                        passed = None
                    else:
                        await _rollback_reserved_redis(reserved)
                        reserved.clear()
                        await _refresh_offer_caps(db, caps)
                        return _result(False, "cap_check_error")

                if passed is False:
                    logger.warning(
                        f"每日Cap超限: offer={cap.offer_id}, limit={cap.daily_cap}, "
                        f"current={redis_init_val}"
                    )
                    await _rollback_reserved_redis(reserved)
                    reserved.clear()
                    await _refresh_offer_caps(db, caps)
                    return _result(False, "cap_exceeded")

                if passed is True or passed is None:
                    # Redis fail-open 时仍更新 DB 计数作为降级权威值，但不能把未确认写入的
                    # Redis 操作登记为 reservation，避免事务回滚时误减其它请求的计数。
                    if passed is True:
                        reserved.append(("daily", cap.offer_id, cap.publisher_id, today_start, reservation_id))
                    if is_new_day:
                        cap.cap_start_date = today_start
                    cap.current_daily_count = redis_init_val + 1
            
            # 3. 处理总计数（Redis 先预留，成功后再更新 DB）
            if cap.total_cap:
                redis_init_val = cap.current_total_count or 0

                reservation_id = uuid.uuid4().hex
                try:
                    passed = await RedisCapManager.check_and_increment_total(
                        cap.offer_id,
                        cap.total_cap,
                        cap.publisher_id,
                        initial_value=redis_init_val,
                        reservation_id=reservation_id,
                    )
                except Exception as e:
                    logger.warning(f"Redis总计数递增同步失败: {e}")
                    if settings.CAP_FAIL_OPEN:
                        logger.warning("Cap 总计数 Redis 失败，fail-open 跳过总计数")
                        passed = None
                    else:
                        await _rollback_reserved_redis(reserved)
                        reserved.clear()
                        await _refresh_offer_caps(db, caps)
                        return _result(False, "cap_check_error")

                if passed is False:
                    logger.warning(
                        f"总Cap超限: offer={cap.offer_id}, limit={cap.total_cap}, "
                        f"current={redis_init_val}"
                    )
                    await _rollback_reserved_redis(reserved)
                    reserved.clear()
                    await _refresh_offer_caps(db, caps)
                    return _result(False, "cap_exceeded")

                if passed is True or passed is None:
                    # 与 daily 一致：fail-open 更新 DB 计数，但只对已确认的 Redis
                    # reservation 执行回滚，防止把其它并发请求的计数减掉。
                    if passed is True:
                        reserved.append(("total", cap.offer_id, cap.publisher_id, None, reservation_id))
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
) -> None:
    """
    DB 事务回滚后同步回退 Redis Cap 计数。

    increment_cap_count 会先写 Redis 再改 DB；外层 rollback 不会撤销 Redis，
    须在转化入库失败或 Cap 递增判定失败时显式调用本函数。
    """
    if not offer_id:
        return
    try:
        query = select(OfferCap).where(
            and_(
                OfferCap.offer_id == offer_id,
                OfferCap.is_active == True,  # noqa: E712
            )
        )
        if publisher_id:
            query = query.where(
                or_(
                    OfferCap.publisher_id == publisher_id,
                    OfferCap.publisher_id.is_(None),
                )
            )
        if advertiser_id:
            query = query.where(
                or_(
                    OfferCap.cap_type == "offer",
                    and_(
                        OfferCap.cap_type == "advertiser_offer",
                        OfferCap.advertiser_id == advertiser_id,
                    ),
                )
            )
        else:
            query = query.where(OfferCap.cap_type == "offer")

        result = await db.execute(query)
        caps = result.scalars().all()
        for cap in caps:
            if cap.daily_cap:
                await RedisCapManager.decrement_daily(cap.offer_id, cap.publisher_id)
            if cap.total_cap:
                await RedisCapManager.decrement_total(cap.offer_id, cap.publisher_id)
    except Exception as e:
        logger.error(
            "回退 Redis Cap 计数失败: offer_id=%s publisher_id=%s err=%s",
            offer_id,
            publisher_id,
            e,
            exc_info=True,
        )


async def reset_daily_caps(db: AsyncSession) -> None:
    """
    重置已跨日的每日 Cap DB 计数。

    使用行锁与 Postback 的 Cap 预留串行化，避免午夜并发请求被重置覆盖。
    不删除 Redis 今日 key：定时任务可能在当天已有流量后才运行，删除今日 key
    会丢失已经发生的 reservation。历史日期 key 由 TTL 自然回收。
    """
    try:
        now = get_app_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        query = (
            select(OfferCap)
            .where(
                and_(
                    OfferCap.is_active == True,
                    OfferCap.daily_cap > 0,
                    or_(
                        OfferCap.cap_start_date.is_(None),
                        OfferCap.cap_start_date < today_start,
                    ),
                )
            )
            .with_for_update()
        )
        result = await db.execute(query)
        caps_to_reset = result.scalars().all()

        # 行锁保证与 increment_cap_count 的 SELECT ... FOR UPDATE 串行执行。
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
