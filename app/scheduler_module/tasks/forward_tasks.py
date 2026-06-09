"""
Postback 下游转发定时任务模块。

功能说明：
- 消费 ``PostbackForwardQueue`` 待转发记录，将转化回传至下游渠道（Publisher）postback URL
- 失败时指数退避：递增 retry_count、推迟 next_retry_time；超限移出队列并记 PostbackForwardLog
- ``trigger_forward_processing`` 供 Postback 入队后 fire-and-forget 立即触发

典型触发方式：
- Cron 周期性执行 ``process_forward_queue``
- 单笔入队后异步调用 ``trigger_forward_processing`` 降低延迟

在系统中的位置：
- 委托 ``app.core.postback.forwarder.PostbackForwarder`` 执行 HTTP 转发

注意事项：
1. 转发 URL 占位符替换规则与 Offer Tracklink 一致
2. 队列积压时监控 retry_count 分布，防止下游长时间不可用导致 Redis/DB 膨胀
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

# 单条任务最大重试次数，超过后从队列删除
MAX_RETRIES = 5
# 每轮调度最多处理的队列条数，避免单次执行过长
BATCH_SIZE = 50

# 指数退避间隔（秒）：第 1~5 次重试分别等待 1 分钟、5 分钟、15 分钟、1 小时、2 小时
RETRY_DELAYS = [60, 300, 900, 3600, 7200]


async def trigger_forward_processing():
    """
    触发转发处理（Fire-and-Forget 入口）。

    通常由 Postback Processor 在转化入队后立即异步调用，
    内部委托 process_forward_queue；异常仅记录日志，不向上抛出，
    避免影响主 Postback 响应链路。
    """
    try:
        await process_forward_queue()
    except Exception as e:
        logger.error(f"触发转发处理任务失败: {e}", exc_info=True)


async def process_forward_queue():
    """
    定时任务：批量处理转发队列。

    查询 next_retry_time <= 当前应用时间的待处理任务（按重试时间升序），
    每批最多 BATCH_SIZE 条，逐条调用 process_single_task 串行处理。

    说明:
        next_retry_time 存储为北京时间（naive），与 get_app_now_naive 一致。
        若本批处理后仍有积压，依赖下一轮调度继续消费。
    """
    try:
        async with AsyncSessionLocal() as db:
            # ---------- 1. 查询到期可执行的任务 ----------
            now = get_app_now_naive()
            query = select(PostbackForwardQueue).where(
                PostbackForwardQueue.next_retry_time <= now
            ).order_by(PostbackForwardQueue.next_retry_time).limit(BATCH_SIZE)

            result = await db.execute(query)
            tasks = result.scalars().all()

            if not tasks:
                return

            logger.info(f"开始处理转发队列，任务数: {len(tasks)}")

            # ---------- 2. 逐条处理（共享同一 Session，避免并发会话冲突） ----------
            for task in tasks:
                await process_single_task(db, task)

    except Exception as e:
        logger.error(f"转发队列处理任务异常: {e}", exc_info=True)


async def process_single_task(db: AsyncSession, task: PostbackForwardQueue):
    """
    处理单条转发队列记录。

    加载关联的 PostbackConversion 与 Product，调用 PostbackForwarder.forward_to_downstream
    执行 HTTP 回传（自动附带原始点击参数并过滤占位符）。根据最新 ForwardLog 判定成败：
    - 成功：从队列删除
    - 失败且未超重试上限：递增 retry_count，按 RETRY_DELAYS 设置 next_retry_time
    - 失败且已达上限：从队列删除（失败详情已在 ForwardLog）

    参数:
        db: 异步数据库会话
        task: PostbackForwardQueue 队列行
    """
    try:
        # ---------- 1. 加载转化与产品（转发目标 URL 等依赖 Product） ----------
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
            # 关联数据已删除，队列记录无意义，直接清理
            await db.delete(task)
            await db.commit()
            return

        # ---------- 2. 执行下游转发 ----------
        try:
            await PostbackForwarder.forward_to_downstream(conversion, product, db)

            # ---------- 3. 根据最新 ForwardLog 判断成败 ----------
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
                # 失败：按重试策略更新或丢弃
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
        except Exception as forward_err:
            # forward_to_downstream 抛出异常时，仍按相同重试规则处理队列项
            logger.error(
                f"调用 forward_to_downstream 失败: queue_id={task.id}, "
                f"conversion_id={task.conversion_id}, error={str(forward_err)}",
                exc_info=True
            )
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
