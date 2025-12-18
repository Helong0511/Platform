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
                # 统计今日转化数量（从实际转化记录统计）
                now = datetime.now(timezone.utc)
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                
                # 通过 Click 记录关联统计今日转化
                # 注意：这里需要 PostbackConversion 有 click_id 字段
                # 如果字段不存在，使用 current_daily_count
                if hasattr(PostbackConversion, 'click_id'):
                    # 从实际转化记录统计
                    conversion_count_query = select(func.count(PostbackConversion.id)).join(
                        Click, PostbackConversion.click_id == Click.click_id
                    ).where(
                        and_(
                            Click.offer_id == offer_id,
                            Click.click_time >= today_start,
                            Click.click_time < now
                        )
                    )
                    if publisher_id:
                        conversion_count_query = conversion_count_query.where(Click.publisher_id == publisher_id)
                    if advertiser_id:
                        conversion_count_query = conversion_count_query.where(Click.advertiser_id == advertiser_id)
                    
                    actual_count = (await db.execute(conversion_count_query)).scalar() or 0
                else:
                    # 使用缓存的计数
                    actual_count = cap.current_daily_count
                
                if actual_count >= cap.daily_cap:
                    return False, f"已达到每日Cap限制: {cap.daily_cap} (当前: {actual_count})"
            
            # 检查总 Cap
            if cap.total_cap:
                # 优先从实际转化记录统计（更准确）
                if hasattr(PostbackConversion, 'click_id') and hasattr(PostbackConversion, 'conversion_status'):
                    # 从实际转化记录统计总转化（只统计 Approved 状态的转化）
                    total_count_query = select(func.count(PostbackConversion.id)).join(
                        Click, PostbackConversion.click_id == Click.click_id
                    ).where(
                        and_(
                            Click.offer_id == offer_id,
                            PostbackConversion.conversion_status == 'Approved'  # 只统计已批准的转化
                        )
                    )
                    if publisher_id:
                        total_count_query = total_count_query.where(Click.publisher_id == publisher_id)
                    if advertiser_id:
                        total_count_query = total_count_query.where(Click.advertiser_id == advertiser_id)
                    if cap.cap_start_date:
                        total_count_query = total_count_query.where(Click.click_time >= cap.cap_start_date)
                    
                    actual_total_count = (await db.execute(total_count_query)).scalar() or 0
                else:
                    # 使用缓存的计数
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
) -> None:
    """
    增加 Cap 计数
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        publisher_id: 渠道ID（可选）
        advertiser_id: 广告主ID（可选）
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
        
        for cap in caps:
            # 增加每日计数
            if cap.daily_cap:
                # 检查是否需要重置（新的一天）
                if cap.cap_start_date and cap.cap_start_date.date() < today_start.date():
                    cap.current_daily_count = 0
                    cap.cap_start_date = today_start
                cap.current_daily_count += 1
            
            # 增加总计数
            if cap.total_cap:
                if not cap.cap_start_date:
                    cap.cap_start_date = now
                cap.current_total_count += 1
        
        await db.commit()
    except Exception as e:
        logger.error(f"增加Cap计数失败: {str(e)}", exc_info=True)
        await db.rollback()


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

