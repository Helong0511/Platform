"""
Cap DB/Redis 同步模块

确保 Redis 和数据库的 Cap 计数保持一致
使用 Redis 为权威源，定期同步到 DB
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.models.models import OfferCap
from app.core.redis_client import get_redis_client
from app.core.cap.redis_counter import get_daily_cap_key, get_total_cap_key
from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)


class CapSynchronizer:
    """
    Offer Cap 计数同步器：以 Redis 为权威源，将每日/总 Cap 计数写回数据库。

    供定时任务或管理端手动触发，保证 DB 中的 ``current_daily_count`` /
    ``current_total_count`` 与 Redis 键 ``cpl:cap:*`` 一致。
    """

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 异步数据库会话，用于查询与更新 OfferCap 记录
        """
        self.db = db
    
    async def sync_all_active_caps(self) -> Dict[str, int]:
        """
        同步所有活跃的 Cap 配置
        
        Returns:
            dict: 同步统计信息
        """
        redis = await get_redis_client()
        if not redis:
            logger.warning("Redis 不可用，跳过 Cap 同步")
            return {'success': 0, 'failed': 0}
        
        # 查询所有活跃的 Cap 配置
        result = await self.db.execute(
            select(OfferCap).where(OfferCap.is_active == True)
        )
        caps = result.scalars().all()
        
        stats = {'success': 0, 'failed': 0}
        now = get_app_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        for cap in caps:
            try:
                # 同步每日 Cap
                if cap.daily_cap:
                    redis_key = get_daily_cap_key(cap.offer_id, now, cap.publisher_id)
                    redis_count = await redis.get(redis_key)
                    
                    if redis_count is not None:
                        # Redis 有数据，同步到 DB
                        cap.current_daily_count = int(redis_count)
                        
                        # 检查是否需要重置（新的一天）
                        if cap.cap_start_date and cap.cap_start_date.date() != today_start.date():
                            # 新的一天，重置计数
                            cap.current_daily_count = 0
                            await redis.setex(redis_key, 48*3600, 0)
                
                # 同步总 Cap
                if cap.total_cap:
                    redis_key = get_total_cap_key(cap.offer_id, cap.publisher_id)
                    redis_count = await redis.get(redis_key)
                    
                    if redis_count is not None:
                        cap.current_total_count = int(redis_count)
                
                stats['success'] += 1
                
            except Exception as e:
                logger.error(f"同步 Cap 失败：cap_id={cap.id}, error={e}", exc_info=True)
                stats['failed'] += 1
        
        # 提交数据库更新
        try:
            await self.db.commit()
            logger.info(f"Cap 同步完成：成功 {stats['success']}/{len(caps)}, 失败 {stats['failed']}")
        except Exception as e:
            logger.error(f"提交 Cap 同步失败：{e}", exc_info=True)
            await self.db.rollback()
        
        return stats
    
    async def sync_single_cap(self, cap_id: int) -> bool:
        """
        同步单个 Cap 配置
        
        Args:
            cap_id: Cap ID
        
        Returns:
            bool: 是否成功
        """
        redis = await get_redis_client()
        if not redis:
            return False
        
        try:
            # 查询 Cap 配置
            result = await self.db.execute(
                select(OfferCap).where(OfferCap.id == cap_id)
            )
            cap = result.scalars().first()
            
            if not cap:
                logger.warning(f"Cap 配置不存在：cap_id={cap_id}")
                return False
            
            now = get_app_now_naive()
            
            # 同步每日 Cap
            if cap.daily_cap:
                redis_key = get_daily_cap_key(cap.offer_id, now, cap.publisher_id)
                redis_count = await redis.get(redis_key)
                
                if redis_count is not None:
                    cap.current_daily_count = int(redis_count)
            
            # 同步总 Cap
            if cap.total_cap:
                redis_key = get_total_cap_key(cap.offer_id, cap.publisher_id)
                redis_count = await redis.get(redis_key)
                
                if redis_count is not None:
                    cap.current_total_count = int(redis_count)
            
            await self.db.commit()
            logger.info(f"单个 Cap 同步成功：cap_id={cap_id}")
            return True
            
        except Exception as e:
            logger.error(f"同步单个 Cap 失败：cap_id={cap_id}, error={e}", exc_info=True)
            await self.db.rollback()
            return False
    
    async def cleanup_expired_caps(self) -> int:
        """
        清理过期的 Cap 缓存
        
        Returns:
            int: 清理数量
        """
        redis = await get_redis_client()
        if not redis:
            return 0
        
        try:
            # 扫描所有 Cap 相关的 Key
            cursor = 0
            cleaned_count = 0
            pattern = "cpl:cap:*"
            
            while True:
                cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                
                if keys:
                    # 检查每个 Key 是否过期
                    for key in keys:
                        ttl = await redis.ttl(key)
                        if ttl == -2:  # Key 不存在
                            continue
                        if ttl < 0:  # 没有过期时间，设置一个
                            await redis.expire(key, 7*24*3600)  # 7 天
                            cleaned_count += 1
                
                if cursor == 0:
                    break
            
            logger.info(f"清理过期 Cap 缓存完成：{cleaned_count} 个")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理过期 Cap 缓存失败：{e}", exc_info=True)
            return 0


async def schedule_cap_sync(db: AsyncSession, interval_minutes: int = 5):
    """
    定时同步 Cap（建议在 scheduler 中调用）
    
    Args:
        db: 数据库会话
        interval_minutes: 同步间隔（分钟）
    """
    synchronizer = CapSynchronizer(db)
    
    # 立即执行一次
    stats = await synchronizer.sync_all_active_caps()
    
    # 记录告警（如果失败率高）
    total = stats['success'] + stats['failed']
    if total > 0 and stats['failed'] / total > 0.2:
        logger.warning(f"Cap 同步失败率过高：{stats['failed']}/{total} ({stats['failed']/total*100:.1f}%)")


async def get_cap_sync_status(db: AsyncSession) -> Dict:
    """
    获取 Cap 同步状态
    
    Args:
        db: 数据库会话
    
    Returns:
        dict: 同步状态
    """
    redis = await get_redis_client()
    
    # 查询 DB 中的 Cap 数量
    result = await db.execute(
        select(OfferCap).where(OfferCap.is_active == True)
    )
    db_caps = result.scalars().all()
    
    # 查询 Redis 中的 Cap Key 数量
    redis_count = 0
    if redis:
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match="cpl:cap:*", count=100)
            redis_count += len(keys)
            if cursor == 0:
                break
    
    return {
        'db_caps': len(db_caps),
        'redis_keys': redis_count,
        'sync_status': 'healthy' if redis_count >= len(db_caps) * 0.8 else 'warning',
        'timestamp': datetime.now().isoformat()
    }
