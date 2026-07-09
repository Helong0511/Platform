"""
Cap 管理逻辑
用于检查 Cap 限制和自动下线
"""
import logging
from typing import Optional, Tuple
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from sqlalchemy import update
from app.models.models import OfferCap, Offer, PostbackConversion

logger = logging.getLogger(__name__)

from app.core.cap.redis_counter import RedisCapManager, get_daily_cap_key, get_total_cap_key
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
                        # 使用原子 SQL 查询避免大表 COUNT
                        # 注意：这里为了性能，如果 DB 也很大，可以直接信任 OfferCap 表的缓存字段 current_daily_count
                        # 或者只在 Redis 失效时查一次大表
                        if cap.cap_start_date and cap.cap_start_date.date() == today_start.date():
                             actual_count = cap.current_daily_count
                        else:
                             actual_count = 0
                        
                        # 回写 Redis (设置过期时间)
                        try:
                            await redis.setex(redis_key, 48 * 3600, actual_count)
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
            
            # 检查总 Cap
            if cap.total_cap:
                # 使用 DB 缓存字段优化
                actual_total_count = cap.current_total_count
                if actual_total_count >= cap.total_cap:
                     return False, f"已达到总Cap限制: {cap.total_cap} (当前: {actual_total_count})"
        
        return True, None
    except Exception as e:
        logger.error(f"检查Cap失败: {str(e)}", exc_info=True)
        # 出错时允许通过，避免影响正常流程
        return True, None


async def increment_cap_count(
    db: AsyncSession,
    offer_id: int,
    publisher_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    *,
    session_flush: bool = True,
) -> bool:
    """
    增加 Cap 计数 (线程/进程安全版本)
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        publisher_id: 渠道ID（可选）
        advertiser_id: 广告主ID（可选）
        
    Returns:
        bool: True=计数增加成功且未超限, False=计数增加后发现超限
    """
    try:
        # 1. 查询所有相关的 Cap 配置，使用 with_for_update() 进行行级锁定
        # 这一步非常重要，确保在并发环境下，同一时间只有一个进程在处理此 Cap 配置的更新
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
        caps = result.scalars().all()
        
        now = get_app_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        all_passed = True
        
        for cap in caps:
            # 2. 处理每日计数
            if cap.daily_cap:
                # 检查是否需要重置（新的一天）
                if not cap.cap_start_date or cap.cap_start_date.date() < today_start.date():
                    cap.current_daily_count = 0
                    cap.cap_start_date = today_start
                    # 重置时，Redis 的 initial_value 应为 0
                    redis_init_val = 0
                else:
                    # 正常递增，传递当前 DB 的值作为冷启动初始值
                    redis_init_val = cap.current_daily_count
                
                # DB 更新 (由于有 with_for_update，这里是安全的)
                cap.current_daily_count += 1

                # ====== 优化：Redis 原子递增并同步 DB 初始值 ======
                try:
                    passed = await RedisCapManager.check_and_increment_daily(
                         cap.offer_id, cap.daily_cap, cap.publisher_id,
                         initial_value=redis_init_val
                    )
                    if not passed:
                        all_passed = False
                        logger.warning(f"每日Cap超限: offer={cap.offer_id}, limit={cap.daily_cap}, current={cap.current_daily_count}")
                except Exception as e:
                    logger.warning(f"Redis计数递增同步失败: {e}")
            
            # 3. 处理总计数
            if cap.total_cap:
                if not cap.cap_start_date:
                    cap.cap_start_date = now
                
                redis_init_val = cap.current_total_count
                cap.current_total_count += 1
                
                # Redis 更新 (Total Cap)
                try:
                    passed = await RedisCapManager.check_and_increment_total(
                        cap.offer_id, cap.total_cap, cap.publisher_id,
                        initial_value=redis_init_val
                    )
                    if not passed:
                        all_passed = False
                        logger.warning(f"总Cap超限: offer={cap.offer_id}, limit={cap.total_cap}, current={cap.current_total_count}")
                except Exception as e:
                    logger.warning(f"Redis总计数递增同步失败: {e}")
        
        # 由调用方控制外层事务时可选跳过 flush，与转化入库同一 commit
        if session_flush:
            await db.flush()
        return all_passed
        
    except Exception as e:
        logger.error(f"增加Cap计数失败: {str(e)}", exc_info=True)
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
    重置每日 Cap 计数（定时任务调用）
    使用批量更新以提高性能和原子性
    同时清除Redis中的每日Cap计数
    
    Args:
        db: 数据库会话
    """
    try:
        now = get_app_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 1. 查询所有需要重置的 Cap 配置（用于清除Redis）
        query = select(OfferCap).where(
            and_(
                OfferCap.is_active == True,
                OfferCap.daily_cap > 0,
                or_(
                    OfferCap.cap_start_date.is_(None),
                    OfferCap.cap_start_date < today_start
                )
            )
        )
        result = await db.execute(query)
        caps_to_reset = result.scalars().all()
        
        # 2. 清除Redis中的每日Cap计数
        redis = await get_redis_client()
        if redis:
            try:
                # 清除今天和昨天的key（防止时区问题）
                for date_offset in [0, -1]:
                    reset_date = today_start + timedelta(days=date_offset)
                    for cap in caps_to_reset:
                        # 清除所有渠道的每日Cap key
                        # 包括特定渠道和全局渠道的key
                        keys_to_delete = []
                        
                        # 全局渠道key
                        global_key = get_daily_cap_key(cap.offer_id, reset_date, None)
                        keys_to_delete.append(global_key)
                        
                        # 如果有特定渠道，也需要清除（虽然可能不存在，但为了安全）
                        if cap.publisher_id:
                            pub_key = get_daily_cap_key(cap.offer_id, reset_date, cap.publisher_id)
                            keys_to_delete.append(pub_key)
                        
                        # 批量删除
                        for key in keys_to_delete:
                            try:
                                await redis.delete(key)
                            except Exception as e:
                                logger.warning(f"清除Redis key失败: {key}, error: {e}")
                
                logger.info(f"成功清除Redis中的每日Cap计数，涉及 {len(caps_to_reset)} 个Cap配置")
            except Exception as e:
                logger.warning(f"清除Redis每日Cap计数时出错: {e}，继续执行DB重置")
        else:
            logger.warning("Redis不可用，跳过清除Redis计数")
        
        # 3. 批量更新数据库
        stmt = (
            update(OfferCap)
            .where(
                and_(
                    OfferCap.is_active == True,
                    OfferCap.daily_cap > 0,
                    or_(
                        OfferCap.cap_start_date.is_(None),
                        OfferCap.cap_start_date < today_start
                    )
                )
            )
            .values(
                current_daily_count=0,
                cap_start_date=today_start
            )
        )
        
        result = await db.execute(stmt)
        await db.commit()
        
        logger.info(f"成功执行批量每日Cap重置，更新了 {result.rowcount} 条记录")
        
    except Exception as e:
        logger.error(f"批量重置每日Cap失败: {str(e)}", exc_info=True)
        await db.rollback()
        raise
