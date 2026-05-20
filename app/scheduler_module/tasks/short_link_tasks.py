"""
短链接相关定时任务
定期同步点击次数到数据库，批量处理点击记录队列
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.database import AsyncSessionLocal
from app.core.short_link_click_counter import sync_click_counts_to_db
from app.scheduler_module.tasks.clicks_batch_processor import process_clicks_queue
from app.models.models import ShortLink
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from sqlalchemy import update, select, and_, exists

logger = logging.getLogger(__name__)

TASK_SYNC_CLICKS = "短链接点击次数同步"
TASK_PROCESS_QUEUE = "点击记录队列批量处理"
TASK_OPEN_LINKS = "每日打开短链接"


async def sync_short_link_clicks_task():
    """
    同步短链接点击次数到数据库
    每5分钟执行一次（cron 见 task_config），将 Redis 中的点击次数批量更新到数据库
    """
    synced_count = 0
    try:
        logger.info("开始执行短链接点击次数同步任务...")
        async with AsyncSessionLocal() as db:
            synced_count = await sync_click_counts_to_db(db)
            if synced_count > 0:
                logger.info(f"✅ 短链接点击次数同步成功: 更新了 {synced_count} 条记录")
            else:
                logger.debug("ℹ️ 短链接点击次数同步: 没有需要更新的记录（Redis中可能没有待同步的计数器）")
        set_task_result(TASK_SYNC_CLICKS, f"执行成功: 同步 {synced_count} 条")
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
    result = {"processed": 0, "inserted": 0}
    try:
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
        set_task_result(
            TASK_PROCESS_QUEUE,
            f"执行成功: 处理={result.get('processed', 0)}, 插入={result.get('inserted', 0)}",
        )
    except Exception as e:
        logger.error(f"❌ 点击记录队列批量处理任务执行失败: {e}", exc_info=True)
        raise


async def open_closed_short_links_task():
    """
    每日自动打开被关闭的短链接
    每天执行一次，将前一天因达到转化上限而关闭的短链接重新激活
    前提是关联的 Offer 处于激活状态
    """
    opened = 0
    try:
        logger.info("开始执行每日打开短链接任务...")
        async with AsyncSessionLocal() as db:
            # 更新所有被关闭的短链接为激活状态，前提是关联的 Offer 处于激活状态
            from app.models.models import Offer
            
            # 构建子查询，获取激活状态的 Offer ID
            active_offer_subquery = exists(
                select(Offer.id)
                .where(
                    and_(
                        Offer.id == ShortLink.offer_id,
                        Offer.is_active == True,
                        Offer.status == 'Active'
                    )
                )
            )
            
            # 更新被关闭且关联的 Offer 是激活状态的短链接
            update_stmt = update(ShortLink).where(
                and_(
                    ShortLink.is_active == False,
                    active_offer_subquery
                )
            ).values(is_active=True)

            result = await db.execute(update_stmt)
            await db.commit()
            opened = result.rowcount or 0
            if opened > 0:
                logger.info(f"✅ 成功打开 {opened} 个被关闭的短链接")
            else:
                logger.debug("ℹ️ 没有需要打开的短链接")

        set_task_result(TASK_OPEN_LINKS, f"执行成功: 打开 {opened} 个短链接")
        logger.debug("每日打开短链接任务执行成功")
    except Exception as e:
        logger.error(f"❌ 每日打开短链接任务执行失败: {e}", exc_info=True)
        raise
