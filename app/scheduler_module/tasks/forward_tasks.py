"""
Postback 下游转发定时任务模块。

功能说明：
- 消费 ``PostbackForwardQueue`` 待转发记录，将转化回传至下游渠道（Publisher）postback URL
- 失败时指数退避：递增 retry_count、推迟 next_retry_time；超限移出队列并记 PostbackForwardLog
- ``trigger_forward_processing`` 供 Postback 入队后 fire-and-forget 立即触发
"""
import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.transformers.click_associator import ClickAssociator
from app.core.utils import get_app_now_naive
from app.models.models import PostbackForwardQueue, PostbackForwardLog, PostbackConversion

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BATCH_SIZE = 50
# 单条任务领取后设置租约，避免多个 Web Worker / Scheduler 同时发送同一转化。
FORWARD_TASK_LEASE_SECONDS = 300
RETRY_DELAYS = [60, 300, 900, 3600, 7200]


def _due_forward_task_query(now):
    """领取一条到期任务；MySQL 8 使用 SKIP LOCKED 避免多消费者重复领取。"""
    return (
        select(PostbackForwardQueue)
        .where(PostbackForwardQueue.next_retry_time <= now)
        .order_by(PostbackForwardQueue.next_retry_time, PostbackForwardQueue.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def _latest_forward_log_query(
    conversion_id: int,
    *,
    publisher_id: int | None = None,
    product_id: int | None = None,
):
    """按稳定顺序读取目标最近一次转发日志，避免同秒日志顺序不确定。"""
    query = (
        select(PostbackForwardLog)
        .where(PostbackForwardLog.conversion_id == conversion_id)
        .order_by(
            PostbackForwardLog.created_at.desc(),
            PostbackForwardLog.id.desc(),
        )
        .limit(1)
    )
    if publisher_id is not None:
        query = query.where(PostbackForwardLog.publisher_id == publisher_id)
    elif product_id is not None:
        query = query.where(
            PostbackForwardLog.product_id == product_id,
            PostbackForwardLog.publisher_id.is_(None),
        )
    return query


async def trigger_forward_processing():
    """Fire-and-Forget 触发转发队列消费。"""
    try:
        await process_forward_queue()
    except Exception as exc:
        logger.error("触发转发处理任务失败：error_type=%s", type(exc).__name__)


async def process_forward_queue():
    """逐条领取并处理到期任务，避免多消费者并发重复发送。"""
    try:
        async with AsyncSessionLocal() as db:
            processed = 0
            while processed < BATCH_SIZE:
                now = get_app_now_naive()
                result = await db.execute(_due_forward_task_query(now))
                task = result.scalars().first()
                if not task:
                    break

                # 在发送外部 HTTP 请求前先提交租约。其它消费者随后看不到该到期任务；
                # 若进程崩溃，租约到期后任务会自动重新进入队列。
                task.next_retry_time = now + timedelta(
                    seconds=FORWARD_TASK_LEASE_SECONDS
                )
                await db.commit()

                logger.info(
                    "已领取转发队列任务：queue_id=%s lease=%ss",
                    task.id,
                    FORWARD_TASK_LEASE_SECONDS,
                )
                await process_single_task(db, task)
                processed += 1

            if processed:
                logger.info("本轮转发队列处理结束：已领取 %s 条任务", processed)
    except Exception as exc:
        logger.error("转发队列处理任务异常：error_type=%s", type(exc).__name__)


async def process_single_task(db: AsyncSession, task: PostbackForwardQueue):
    """处理单条转发队列记录。"""
    try:
        conversion_result = await db.execute(
            select(PostbackConversion).where(PostbackConversion.id == task.conversion_id)
        )
        conversion = conversion_result.scalars().first()
        if not conversion:
            logger.warning("转发任务转化不存在: queue_id=%s", task.id)
            await db.delete(task)
            await db.commit()
            return

        click_association = None
        if conversion.click_id:
            click_association = await ClickAssociator.associate(conversion.click_id, db)

        try:
            if task.publisher_id:
                await PostbackForwarder.forward_to_publisher(
                    conversion, db, click_association=click_association
                )
            elif task.product_id:
                await PostbackForwarder.forward_to_product(
                    conversion, db, click_association=click_association
                )
            else:
                logger.warning(
                    "转发任务缺少 publisher_id/product_id: queue_id=%s",
                    task.id,
                )
                await db.delete(task)
                await db.commit()
                return

            log_query = _latest_forward_log_query(
                task.conversion_id,
                publisher_id=task.publisher_id,
                product_id=task.product_id,
            )
            latest_log = (await db.execute(log_query)).scalars().first()

            if latest_log and latest_log.success:
                await db.delete(task)
                await db.commit()
                logger.info("转发重试成功: queue_id=%s", task.id)
            else:
                await _schedule_or_drop_retry(db, task)
        except Exception as forward_err:
            logger.error(
                "转发重试执行失败：queue_id=%s error_type=%s",
                task.id,
                type(forward_err).__name__,
            )
            await _schedule_or_drop_retry(db, task)
    except Exception as exc:
        logger.error("处理单条转发任务失败：error_type=%s", type(exc).__name__)
        await db.rollback()


async def _schedule_or_drop_retry(db: AsyncSession, task: PostbackForwardQueue) -> None:
    """失败时递增退避或移出队列。"""
    if task.retry_count >= MAX_RETRIES:
        await db.delete(task)
        await db.commit()
        logger.warning("转发任务超过重试上限: queue_id=%s", task.id)
        return
    delay = RETRY_DELAYS[min(task.retry_count, len(RETRY_DELAYS) - 1)]
    task.retry_count += 1
    task.next_retry_time = get_app_now_naive() + timedelta(seconds=delay)
    await db.commit()
    logger.info(
        "转发重试已推迟 (%s/%s): queue_id=%s delay=%ss",
        task.retry_count,
        MAX_RETRIES,
        task.id,
        delay,
    )
