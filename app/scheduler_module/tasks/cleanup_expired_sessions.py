"""
清理过期会话和黑名单记录的定时任务
建议每天凌晨2点执行
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal
from app.models.session import UserSession, TokenBlacklist

logger = logging.getLogger(__name__)


async def cleanup_expired_sessions():
    """
    清理过期会话和黑名单记录
    
    清理规则：
    1. 删除过期超过30天的会话记录
    2. 删除过期超过30天的黑名单记录
    3. 标记超过7天未活动的会话为非活跃
    """
    try:
        async with AsyncSessionLocal() as db:
            # 计算过期时间阈值（30天前）
            expired_threshold = datetime.now(timezone.utc) - timedelta(days=30)
            
            # 计算非活跃时间阈值（7天前）
            inactive_threshold = datetime.now(timezone.utc) - timedelta(days=7)
            
            # 1. 删除过期超过30天的会话记录
            delete_sessions_query = delete(UserSession).where(
                UserSession.expires_at < expired_threshold
            )
            result = await db.execute(delete_sessions_query)
            deleted_sessions_count = result.rowcount
            logger.info(f"清理了 {deleted_sessions_count} 条过期会话记录")
            
            # 2. 删除过期超过30天的黑名单记录
            delete_blacklist_query = delete(TokenBlacklist).where(
                TokenBlacklist.expires_at < expired_threshold
            )
            result = await db.execute(delete_blacklist_query)
            deleted_blacklist_count = result.rowcount
            logger.info(f"清理了 {deleted_blacklist_count} 条过期黑名单记录")
            
            # 3. 标记超过7天未活动的会话为非活跃
            update_query = select(UserSession).where(
                UserSession.is_active == True,
                UserSession.last_activity < inactive_threshold
            )
            result = await db.execute(update_query)
            inactive_sessions = result.scalars().all()
            
            for session in inactive_sessions:
                session.is_active = False
            
            updated_sessions_count = len(inactive_sessions)
            logger.info(f"标记了 {updated_sessions_count} 个非活跃会话")
            
            # 提交事务
            await db.commit()
            
            logger.info(
                f"清理完成：删除了 {deleted_sessions_count} 条会话记录，"
                f"{deleted_blacklist_count} 条黑名单记录，"
                f"标记了 {updated_sessions_count} 个非活跃会话"
            )
            
            return {
                "deleted_sessions": deleted_sessions_count,
                "deleted_blacklist": deleted_blacklist_count,
                "updated_sessions": updated_sessions_count
            }
    except Exception as e:
        logger.error(f"清理过期会话失败: {e}", exc_info=True)
        raise

