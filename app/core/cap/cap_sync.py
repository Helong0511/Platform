"""
Cap DB/Redis 同步模块

确保 Redis 和数据库的 Cap 计数保持一致
使用 Redis 为权威源，定期同步到 DB
"""
import logging
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
            # 同步未执行不能报告为 0 成功、0 失败，否则调度任务会误记为成功。
            logger.error("Redis 不可用，Cap 同步无法完成")
            raise RuntimeError("Redis 不可用，无法完成 Cap 计数同步")
        
        # 查询所有活跃的 Cap 配置
        result = await self.db.execute(
            select(OfferCap)
            .where(OfferCap.is_active == True)
            .order_by(OfferCap.id.asc())
            .with_for_update()
        )
        caps = result.scalars().all()
        
        stats = {"success": 0, "failed": 0, "skipped": 0}
        now = get_app_now_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        for cap in caps:
            missing_counter = False
            try:
                # 同步每日 Cap
                if cap.daily_cap:
                    redis_key = get_daily_cap_key(cap.offer_id, now, cap.publisher_id)
                    redis_count = await redis.get(redis_key)
                    if redis_count is not None:
                        # 当前业务日取 DB/Redis 较大值，防止 Redis 数据回退降低已确认计数。
                        db_daily_count = (
                            cap.current_daily_count or 0
                            if cap.cap_start_date
                            and cap.cap_start_date.date() == today_start.date()
                            else 0
                        )
                        cap.current_daily_count = max(int(redis_count), db_daily_count)
                        cap.cap_start_date = today_start
                    else:
                        # 缺 key 表示没有可同步的 Redis 快照，不将其伪报为成功同步。
                        missing_counter = True

                # 同步总 Cap
                if cap.total_cap:
                    redis_key = get_total_cap_key(cap.offer_id, cap.publisher_id)
                    redis_count = await redis.get(redis_key)
                    if redis_count is not None:
                        cap.current_total_count = max(int(redis_count), cap.current_total_count or 0)
                    else:
                        missing_counter = True

                if missing_counter:
                    stats["skipped"] += 1
                else:
                    stats["success"] += 1

            except Exception as e:
                logger.error("同步 Cap 失败：cap_id=%s, error=%s", cap.id, e, exc_info=True)
                stats["failed"] += 1

        # 任一条记录同步失败时回滚整个批次，避免同一批次部分字段被提交。
        if stats["failed"]:
            try:
                await self.db.rollback()
            except Exception:
                logger.error("Cap 同步失败后的回滚也失败", exc_info=True)
            stats = {"success": 0, "failed": len(caps), "skipped": 0}
            logger.error("Cap 同步批次已整体回滚：共 %s 条", len(caps))
            return stats

        try:
            await self.db.commit()
            logger.info(
                "Cap 同步完成：成功 %s，跳过（Redis key 缺失）%s，失败 %s",
                stats["success"], stats["skipped"], stats["failed"],
            )
        except Exception as e:
            logger.error("提交 Cap 同步失败：%s", e, exc_info=True)
            try:
                await self.db.rollback()
            except Exception:
                logger.error("Cap 同步提交失败后的回滚也失败", exc_info=True)
            stats = {"success": 0, "failed": len(caps), "skipped": 0}

        return stats
    
    async def sync_single_cap(self, cap_id: int) -> bool:
        """
        同步单个 Cap 配置。

        Redis key 缺失代表计数未知：不提交部分字段更新，并返回 False。
        """
        redis = await get_redis_client()
        if not redis:
            logger.error("Redis 不可用，无法同步单个 Cap：cap_id=%s", cap_id)
            return False

        try:
            result = await self.db.execute(
                select(OfferCap)
                .where(OfferCap.id == cap_id)
                .order_by(OfferCap.id.asc())
                .with_for_update()
            )
            cap = result.scalars().first()

            if not cap:
                logger.warning("Cap 配置不存在：cap_id=%s", cap_id)
                await self.db.rollback()
                return False

            now = get_app_now_naive()
            missing_keys = []

            if cap.daily_cap:
                redis_key = get_daily_cap_key(cap.offer_id, now, cap.publisher_id)
                redis_count = await redis.get(redis_key)
                if redis_count is None:
                    missing_keys.append("daily")
                else:
                    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    db_daily_count = (
                        cap.current_daily_count or 0
                        if cap.cap_start_date
                        and cap.cap_start_date.date() == today_start.date()
                        else 0
                    )
                    cap.current_daily_count = max(int(redis_count), db_daily_count)
                    cap.cap_start_date = today_start

            if cap.total_cap:
                redis_key = get_total_cap_key(cap.offer_id, cap.publisher_id)
                redis_count = await redis.get(redis_key)
                if redis_count is None:
                    missing_keys.append("total")
                else:
                    cap.current_total_count = max(
                        int(redis_count), cap.current_total_count or 0
                    )

            if missing_keys:
                await self.db.rollback()
                logger.warning(
                    "单个 Cap 同步跳过：Redis 计数 key 缺失，cap_id=%s, counters=%s",
                    cap_id, ",".join(missing_keys),
                )
                return False

            await self.db.commit()
            logger.info("单个 Cap 同步成功：cap_id=%s", cap_id)
            return True

        except Exception as e:
            logger.error("同步单个 Cap 失败：cap_id=%s, error=%s", cap_id, e, exc_info=True)
            try:
                await self.db.rollback()
            except Exception:
                logger.exception("单个 Cap 同步失败后的回滚也失败：cap_id=%s", cap_id)
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
                        # 不为未知类型的 Cap key 设置 TTL。尤其 total key 必须跨越
                        # 任意 7/30 天窗口持续有效；统一设置 TTL 会使累计限额失效。
                        # 已无 TTL 的 key 保持原状，需由明确的业务生命周期清理。
                        if ttl < 0:
                            logger.debug("保留无 TTL 的 Cap key：%s", key)
                
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
        'timestamp': get_app_now_naive().isoformat()
    }
