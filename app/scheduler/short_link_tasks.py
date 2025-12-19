"""
短链接相关定时任务
定期同步点击次数到数据库
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSessionLocal
from app.core.short_link_click_counter import sync_click_counts_to_db

logger = logging.getLogger(__name__)


async def sync_short_link_clicks_task():
    """
    同步短链接点击次数到数据库
    每5分钟执行一次，将Redis中的点击次数批量更新到数据库
    """
    try:
        logger.info("开始执行短链接点击次数同步任务...")
        
        # 创建数据库会话
        async with AsyncSessionLocal() as db:
            # 同步所有点击次数
            synced_count = await sync_click_counts_to_db(db)
            
            if synced_count > 0:
                logger.info(f"短链接点击次数同步成功: 更新了 {synced_count} 条记录")
            else:
                logger.debug("短链接点击次数同步: 没有需要更新的记录")
        
        logger.info("短链接点击次数同步任务执行成功")
    except Exception as e:
        logger.error(f"短链接点击次数同步任务执行失败: {e}", exc_info=True)
        raise


def get_task_result() -> dict:
    """
    获取任务执行结果
    """
    return {
        "task_name": "sync_short_link_clicks",
        "description": "同步短链接点击次数到数据库",
        "last_run": datetime.now(timezone.utc).isoformat(),
    }

