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

from app.models.models import OfferCap, Offer, Click, PostbackConversion

logger = logging.getLogger(__name__)

from app.core.cap.redis_counter import RedisCapManager, get_daily_cap_key, get_total_cap_key
from app.core.redis_client import get_redis_client


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
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        for cap in caps:
            # 检查每日 Cap
            if cap.daily_cap:
                # ====== 优化：使用 Redis 获取当前计数 ======
                redis = await get_redis_client()
                actual_count = 0
                
                if redis:
                    # 尝试从 Redis 读取
                    now = datetime.now(timezone.utc)
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
    advertiser_id: Optional[int] = None
) -> bool:
    """
    增加 Cap 计数
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        publisher_id: 渠道ID（可选）
        advertiser_id: 广告主ID（可选）
        
    Returns:
        bool: True=计数增加成功且未超限, False=计数增加后发现超限
    """
    try:
        # 查询所有相关的 Cap 配置
        query = select(OfferCap).where(
            and_(
                OfferCap.offer_id == offer_id,
                OfferCap.is_active == True
            )
        )
        
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
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        all_passed = True
        
        for cap in caps:
            # 增加每日计数
            if cap.daily_cap:
                # 检查是否需要重置（新的一天）
                if cap.cap_start_date and cap.cap_start_date.date() < today_start.date():
                    cap.current_daily_count = 0
                    cap.cap_start_date = today_start
                
                # DB 更新
                cap.current_daily_count += 1

                # ====== 优化：Redis 原子递增 ======
                try:
                    # 获取原子递增结果
                    passed = await RedisCapManager.check_and_increment_daily(
                         cap.offer_id, cap.daily_cap, cap.publisher_id
                    )
                    if not passed:
                        all_passed = False
                        logger.warning(f"每日Cap超限: offer={cap.offer_id}, limit={cap.daily_cap}")
                except Exception as e:
                    logger.warning(f"Redis计数递增失败: {e}")
            
            # 增加总计数
            if cap.total_cap:
                if not cap.cap_start_date:
                    cap.cap_start_date = now
                cap.current_total_count += 1
                
                # Redis 更新 (Total Cap)
                try:
                    passed = await RedisCapManager.check_and_increment_total(
                        cap.offer_id, cap.total_cap, cap.publisher_id
                    )
                    if not passed:
                        all_passed = False
                        logger.warning(f"总Cap超限: offer={cap.offer_id}, limit={cap.total_cap}")
                except Exception as e:
                    logger.warning(f"Redis总计数递增失败: {e}")
        
        await db.commit()
        return all_passed
        
    except Exception as e:
        logger.error(f"增加Cap计数失败: {str(e)}", exc_info=True)
        await db.rollback()
        # 如果出错，保守起见返回 True（Fail Open），或者根据策略返回 False
        return True


async def reset_daily_caps(db: AsyncSession) -> None:
    """
    重置每日 Cap 计数（定时任务调用）
    
    Args:
        db: 数据库会话
    """
    try:
        # 查询所有激活的 Cap 配置
        result = await db.execute(
            select(OfferCap).where(OfferCap.is_active == True)
        )
        caps = result.scalars().all()
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        for cap in caps:
            # 如果 cap_start_date 不是今天，重置每日计数
            if cap.cap_start_date and cap.cap_start_date.date() < today_start.date():
                cap.current_daily_count = 0
                cap.cap_start_date = today_start
        
        await db.commit()
        logger.info(f"已重置 {len(caps)} 个Cap配置的每日计数")
    except Exception as e:
        logger.error(f"重置每日Cap计数失败: {str(e)}", exc_info=True)
        await db.rollback()

