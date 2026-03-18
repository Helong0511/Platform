"""
Postback 下游转发任务
负责处理 PostbackForwardQueue 中的任务，包含重试机制
"""
import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.core.postback.forwarder import PostbackForwarder
from app.core.utils import get_app_now_naive
from app.models.models import PostbackForwardQueue, PostbackForwardLog, PostbackConversion, Product

logger = logging.getLogger(__name__)

# 最大重试次数
MAX_RETRIES = 5
# 每次批处理数量
BATCH_SIZE = 50

# 指数退避策略 (秒)
RETRY_DELAYS = [60, 300, 900, 3600, 7200]  # 1m, 5m, 15m, 1h, 2h


async def trigger_forward_processing():
    """
    触发转发处理（通常由 Processor 在入队后直接调用，作为 Fire & Forget 任务）
    """
    try:
        await process_forward_queue()
    except Exception as e:
        logger.error(f"触发转发处理任务失败: {e}", exc_info=True)


async def process_forward_queue():
    """
    定时任务：处理转发队列
    查询 next_retry_time <= now 的任务并执行
    """
    try:
        async with AsyncSessionLocal() as db:
            # 1. 查询待处理任务（使用北京时间比较，因为next_retry_time存储的是北京时间）
            now = get_app_now_naive()
            query = select(PostbackForwardQueue).where(
                PostbackForwardQueue.next_retry_time <= now
            ).order_by(PostbackForwardQueue.next_retry_time).limit(BATCH_SIZE)

            result = await db.execute(query)
            tasks = result.scalars().all()

            if not tasks:
                return

            logger.info(f"开始处理转发队列，任务数: {len(tasks)}")

            # 2. 并行处理
            # 注意：为了避免 Session 冲突，每个任务最好由 Consumer 单独处理或小心管理 Session
            # 这里的简单实现：串行或小批量并行

            for task in tasks:
                await process_single_task(db, task)

            # 如果还有更多任务，可以递归调用或依赖下一次调度
            # 这里简单处理，一次只处理一页

    except Exception as e:
        logger.error(f"转发队列处理任务异常: {e}", exc_info=True)


async def process_single_task(db: AsyncSession, task: PostbackForwardQueue):
    """
    处理单个转发任务
    
    使用 PostbackForwarder.forward_to_downstream 来处理转发，
    这样可以自动包含原始点击参数（已过滤占位符）
    """
    try:
        # 1. 重新加载关联对象（Conversion 和 Product）
        conversion_result = await db.execute(
            select(PostbackConversion).where(PostbackConversion.id == task.conversion_id)
        )
        conversion = conversion_result.scalars().first()

        product_result = await db.execute(
            select(Product).where(Product.id == task.product_id)
        )
        product = product_result.scalars().first()

        if not conversion or not product:
            logger.warning(
                f"转发任务关联对象不存在: queue_id={task.id}, "
                f"conversion_id={task.conversion_id}, product_id={task.product_id}"
            )
            # 删除无效任务
            await db.delete(task)
            await db.commit()
            return

        # 2. 使用 PostbackForwarder 处理转发（会自动包含原始点击参数）
        # 注意：forward_to_downstream 会创建 PostbackForwardLog，我们需要在成功后删除队列任务
        try:
            await PostbackForwarder.forward_to_downstream(conversion, product, db)

            # 3. 检查是否成功（通过查询最新的 ForwardLog）
            log_result = await db.execute(
                select(PostbackForwardLog)
                .where(PostbackForwardLog.conversion_id == task.conversion_id)
                .where(PostbackForwardLog.product_id == task.product_id)
                .order_by(PostbackForwardLog.created_at.desc())
                .limit(1)
            )
            latest_log = log_result.scalars().first()

            if latest_log and latest_log.success:
                # 成功：从队列删除
                await db.delete(task)
                await db.commit()
                logger.info(f"转发任务成功: queue_id={task.id}, conversion_id={task.conversion_id}")
            else:
                # 失败：检查重试次数
                if task.retry_count >= MAX_RETRIES:
                    # 超过最大重试次数：从队列删除（Log 已由 forward_to_downstream 创建）
                    await db.delete(task)
                    await db.commit()
                    logger.warning(
                        f"转发任务最终失败 (超过重试次数): queue_id={task.id}, "
                        f"conversion_id={task.conversion_id}"
                    )
                else:
                    # 还可以重试：更新 retry_count 和 next_retry_time
                    delay = RETRY_DELAYS[min(task.retry_count, len(RETRY_DELAYS) - 1)]
                    task.retry_count += 1
                    task.next_retry_time = get_app_now_naive() + timedelta(seconds=delay)
                    await db.commit()
                    logger.info(
                        f"转发任务失败，安排重试 ({task.retry_count}/{MAX_RETRIES}): "
                        f"queue_id={task.id}, delay={delay}s"
                    )
        except Exception as forward_err:
            # forward_to_downstream 内部异常
            logger.error(
                f"调用 forward_to_downstream 失败: queue_id={task.id}, "
                f"conversion_id={task.conversion_id}, error={str(forward_err)}",
                exc_info=True
            )
            # 检查重试次数
            if task.retry_count >= MAX_RETRIES:
                await db.delete(task)
                await db.commit()
                logger.warning(
                    f"转发任务最终失败 (超过重试次数): queue_id={task.id}, "
                    f"conversion_id={task.conversion_id}"
                )
            else:
                delay = RETRY_DELAYS[min(task.retry_count, len(RETRY_DELAYS) - 1)]
                task.retry_count += 1
                task.next_retry_time = get_app_now_naive() + timedelta(seconds=delay)
                await db.commit()
                logger.info(
                    f"转发任务失败，安排重试 ({task.retry_count}/{MAX_RETRIES}): "
                    f"queue_id={task.id}, delay={delay}s"
                )

    except Exception as e:
        logger.error(f"处理单条转发任务失败: {e}", exc_info=True)
        await db.rollback()
