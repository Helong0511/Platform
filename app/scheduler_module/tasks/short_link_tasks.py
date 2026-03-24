"""
短链接相关定时任务
定期同步点击次数到数据库，批量处理点击记录队列
"""
import logging
from datetime import datetime, timezone

from app.core.database import AsyncSessionLocal
from app.core.short_link_click_counter import sync_click_counts_to_db
from app.scheduler_module.tasks.clicks_batch_processor import process_clicks_queue

logger = logging.getLogger(__name__)


async def sync_short_link_clicks_task():
    """
    同步短链接点击次数到数据库
    每5分钟执行一次，将Redis中的点击次数批量更新到数据库
    """
    try:
        # 详细日志输出到 scheduler.log，不输出到 app.log
        logger.info("开始执行短链接点击次数同步任务...")

        # 创建数据库会话
        async with AsyncSessionLocal() as db:
            # 同步所有点击次数
            synced_count = await sync_click_counts_to_db(db)

            if synced_count > 0:
                logger.info(f"✅ 短链接点击次数同步成功: 更新了 {synced_count} 条记录")
            else:
                logger.debug("ℹ️ 短链接点击次数同步: 没有需要更新的记录（Redis中可能没有待同步的计数器）")

        logger.debug("短链接点击次数同步任务执行成功")
    except Exception as e:
        # 错误日志会输出到 app.log（WARNING 级别）
        logger.error(f"❌ 短链接点击次数同步任务执行失败: {e}", exc_info=True)
        raise


async def process_clicks_queue_task():
    """
    批量处理点击记录队列（高并发优化）
    每10秒执行一次，从Redis队列批量取出点击记录并插入到数据库
    """
    try:
        # 批量处理队列
        result = await process_clicks_queue()

        if result['processed'] > 0:
            # 处理结果输出到 scheduler.log（INFO 级别）
            logger.info(
                f"✅ 点击记录队列处理: "
                f"处理={result['processed']}, "
                f"插入={result['inserted']}, "
                f"失败={result['failed']}, "
                f"队列剩余={result['queue_remaining']}"
            )
        # 队列为空时不输出日志
    except Exception as e:
        # 错误日志会输出到 app.log（WARNING 级别）
        logger.error(f"❌ 点击记录队列批量处理任务执行失败: {e}", exc_info=True)
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
