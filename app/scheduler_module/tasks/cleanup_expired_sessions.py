"""
清理过期会话和黑名单记录的定时任务
建议每天凌晨2点执行
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete, update

from app.core.database import AsyncSessionLocal
from app.models.session import UserSession, TokenBlacklist
from app.scheduler_module.task_names import CLEANUP_SESSIONS_TASK_NAME

logger = logging.getLogger(__name__)

# 任务执行结果存储（用于保存到last_error字段）
# key: 任务名称, value: 执行结果信息
_task_results: dict[str, str] = {}


def get_task_result(task_name: str) -> str | None:
    """获取任务执行结果"""
    return _task_results.get(task_name)


def set_task_result(task_name: str, result: str) -> None:
    """设置任务执行结果"""
    _task_results[task_name] = result


async def cleanup_expired_sessions():
    """
    清理过期会话和黑名单记录
    
    清理规则：
    1. 删除过期超过30天的会话记录
    2. 删除过期超过30天的黑名单记录
    3. 标记超过7天未活动的会话为非活跃
    
    Returns:
        dict: 清理结果统计
        {
            "deleted_sessions": 删除的会话记录数,
            "deleted_blacklist": 删除的黑名单记录数,
            "updated_sessions": 标记为非活跃的会话数
        }
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

            # 3. 标记超过7天未活动的会话为非活跃（使用批量更新提高性能）
            update_stmt = update(UserSession).where(
                UserSession.is_active.is_(True),  # 使用 is_() 方法更安全
                UserSession.last_activity < inactive_threshold
            ).values(is_active=False)
            result = await db.execute(update_stmt)
            updated_sessions_count = result.rowcount
            logger.info(f"标记了 {updated_sessions_count} 个非活跃会话")

            # 提交事务
            await db.commit()

            result_summary = (
                f"删除了 {deleted_sessions_count} 条会话记录, "
                f"{deleted_blacklist_count} 条黑名单记录, "
                f"标记了 {updated_sessions_count} 个非活跃会话"
            )

            logger.info(f"清理完成：{result_summary}")

            # 保存执行结果到全局存储（用于保存到last_error字段）
            set_task_result(CLEANUP_SESSIONS_TASK_NAME, f"执行成功: {result_summary}")

            return {
                "deleted_sessions": deleted_sessions_count,
                "deleted_blacklist": deleted_blacklist_count,
                "updated_sessions": updated_sessions_count
            }
    except Exception as e:
        error_msg = f"清理过期会话失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        # 保存错误结果到全局存储
        set_task_result(CLEANUP_SESSIONS_TASK_NAME, error_msg)
        raise
