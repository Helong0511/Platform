"""
Cap计数一致性校验工具
用于校验DB和Redis中的Cap计数是否一致
"""
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import OfferCap
from app.core.cap.redis_counter import get_daily_cap_key, get_total_cap_key
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


async def check_cap_consistency(
    db: AsyncSession,
    offer_id: int = None,
    fix_inconsistencies: bool = False
) -> List[Dict[str, Any]]:
    """
    检查Cap计数一致性
    
    Args:
        db: 数据库会话
        offer_id: 可选的Offer ID，如果提供则只检查该Offer的Cap
        fix_inconsistencies: 是否自动修复不一致的数据
        
    Returns:
        不一致的记录列表，每个记录包含：
        - cap_id: Cap配置ID
        - offer_id: Offer ID
        - publisher_id: 渠道ID
        - db_daily_count: DB中的每日计数
        - redis_daily_count: Redis中的每日计数
        - db_total_count: DB中的总计数
        - redis_total_count: Redis中的总计数
        - inconsistencies: 不一致的类型列表
    """
    inconsistencies = []
    
    try:
        # 查询Cap配置
        query = select(OfferCap).where(OfferCap.is_active == True)
        if offer_id:
            query = query.where(OfferCap.offer_id == offer_id)
        
        result = await db.execute(query)
        caps = result.scalars().all()
        
        redis = await get_redis_client()
        if not redis:
            logger.warning("Redis不可用，无法进行一致性检查")
            return inconsistencies
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        for cap in caps:
            cap_issues = []
            
            # 检查每日Cap
            if cap.daily_cap:
                redis_key = get_daily_cap_key(cap.offer_id, now, cap.publisher_id)
                redis_val = await redis.get(redis_key)
                redis_daily_count = int(redis_val) if redis_val else 0
                
                # 获取DB计数（考虑是否需要重置）
                if cap.cap_start_date and cap.cap_start_date.date() == today_start.date():
                    db_daily_count = cap.current_daily_count
                else:
                    db_daily_count = 0
                
                if redis_daily_count != db_daily_count:
                    cap_issues.append(f"每日计数不一致: DB={db_daily_count}, Redis={redis_daily_count}")
                    
                    if fix_inconsistencies:
                        # 修复：以DB为准，更新Redis
                        try:
                            await redis.setex(redis_key, 48 * 3600, db_daily_count)
                            logger.info(f"已修复每日计数不一致: cap_id={cap.id}, 设置为{db_daily_count}")
                        except Exception as e:
                            logger.error(f"修复每日计数失败: cap_id={cap.id}, error={e}")
            
            # 检查总Cap
            if cap.total_cap:
                redis_key = get_total_cap_key(cap.offer_id, cap.publisher_id)
                redis_val = await redis.get(redis_key)
                redis_total_count = int(redis_val) if redis_val else 0
                db_total_count = cap.current_total_count
                
                if redis_total_count != db_total_count:
                    cap_issues.append(f"总计数不一致: DB={db_total_count}, Redis={redis_total_count}")
                    
                    if fix_inconsistencies:
                        # 修复：以DB为准，更新Redis
                        try:
                            await redis.setex(redis_key, 30 * 24 * 3600, db_total_count)
                            logger.info(f"已修复总计数不一致: cap_id={cap.id}, 设置为{db_total_count}")
                        except Exception as e:
                            logger.error(f"修复总计数失败: cap_id={cap.id}, error={e}")
            
            if cap_issues:
                inconsistencies.append({
                    "cap_id": cap.id,
                    "offer_id": cap.offer_id,
                    "publisher_id": cap.publisher_id,
                    "db_daily_count": cap.current_daily_count if cap.daily_cap else None,
                    "redis_daily_count": redis_daily_count if cap.daily_cap else None,
                    "db_total_count": cap.current_total_count if cap.total_cap else None,
                    "redis_total_count": redis_total_count if cap.total_cap else None,
                    "inconsistencies": cap_issues
                })
        
        if inconsistencies:
            logger.warning(f"发现 {len(inconsistencies)} 个Cap计数不一致")
        else:
            logger.info("Cap计数一致性检查通过")
        
        return inconsistencies
        
    except Exception as e:
        logger.error(f"Cap计数一致性检查失败: {str(e)}", exc_info=True)
        raise

