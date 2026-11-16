"""
Postback 下游转发定时任务模块。

功能说明：
- 消费 ``PostbackForwardQueue`` 待转发记录，将转化回传至下游渠道（Publisher）postback URL
- 失败时指数退避：递增 retry_count、推迟 next_retry_time；超限移出队列并记 PostbackForwardLog
- ``trigger_forward_processing`` 供 Postback 入队后 fire-and-forget 立即触发
"""
import logging
import secrets

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, delete, or_, update
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.transformers.click_associator import ClickAssociator
from app.core.utils import get_app_now_sql_expression
from app.models.models import PostbackForwardQueue, PostbackForwardLog, PostbackConversion

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BATCH_SIZE = 50
# 单条任务领取后设置租约，避免多个 Web Worker / Scheduler 同时发送同一转化。
FORWARD_TASK_LEASE_SECONDS = 300
RETRY_DELAYS = [60, 300, 900, 3600, 7200]


def _due_forward_task_query():
    """只领取业务重试已到期且租约为空/过期的任务；时间统一使用数据库时钟。"""
    db_now = get_app_now_sql_expression()
    return (
        select(PostbackForwardQueue)
        .where(
            PostbackForwardQueue.next_retry_time <= db_now,
            or_(
                PostbackForwardQueue.lease_token.is_(None),
                PostbackForwardQueue.lease_expires_at <= db_now,
            ),
        )
        .order_by(PostbackForwardQueue.next_retry_time, PostbackForwardQueue.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


async def _renew_forward_task_lease(db: AsyncSession, task_id: int, lease_token: str) -> bool:
    """发送前以令牌和未过期条件续租；旧 Worker 无法续租已被接管的任务。"""
    db_now = get_app_now_sql_expression()
    result = await db.execute(
        update(PostbackForwardQueue)
        .where(
            PostbackForwardQueue.id == task_id,
            PostbackForwardQueue.lease_token == lease_token,
            PostbackForwardQueue.lease_expires_at > db_now,
        )
        .values(lease_expires_at=get_app_now_sql_expression(FORWARD_TASK_LEASE_SECONDS))
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return result.rowcount == 1


async def _delete_owned_forward_task(db: AsyncSession, task_id: int, lease_token: str) -> bool:
    """仅允许当前且未过期的租约删除队列任务。"""
    db_now = get_app_now_sql_expression()
    result = await db.execute(
        delete(PostbackForwardQueue).where(
            PostbackForwardQueue.id == task_id,
            PostbackForwardQueue.lease_token == lease_token,
            PostbackForwardQueue.lease_expires_at > db_now,
        )
    )
    await db.commit()
    return result.rowcount == 1

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
    """逐条领取并处理到期任务；业务重试时间与 Worker 租约完全分离。"""
    try:
        async with AsyncSessionLocal() as db:
            processed = 0
            while processed < BATCH_SIZE:
                result = await db.execute(_due_forward_task_query())
                task = result.scalars().first()
                if not task:
                    break

                lease_token = secrets.token_hex(16)
                task.lease_token = lease_token
                task.lease_expires_at = get_app_now_sql_expression(FORWARD_TASK_LEASE_SECONDS)
                await db.commit()
                logger.info("已领取转发队列任务：queue_id=%s lease=%ss", task.id, FORWARD_TASK_LEASE_SECONDS)
                await process_single_task(db, task, lease_token=lease_token)
                processed += 1

            if processed:
                logger.info("本轮转发队列处理结束：已领取 %s 条任务", processed)
    except Exception as exc:
        logger.error("转发队列处理任务异常：error_type=%s", type(exc).__name__)

async def process_single_task(db: AsyncSession, task: PostbackForwardQueue, *, lease_token: str | None = None):
    """处理单条转发队列记录；所有状态变更必须携带当前租约令牌。"""
    lease_token = lease_token or getattr(task, "lease_token", None)
    if not lease_token:
        logger.warning("转发任务缺少租约令牌，拒绝处理：queue_id=%s", task.id)
        return
    try:
        if not await _renew_forward_task_lease(db, task.id, lease_token):
            logger.info("转发任务租约已失效，放弃处理：queue_id=%s", task.id)
            return

        conversion_result = await db.execute(
            select(PostbackConversion).where(PostbackConversion.id == task.conversion_id)
        )
        conversion = conversion_result.scalars().first()
        if not conversion:
            await _delete_owned_forward_task(db, task.id, lease_token)
            logger.warning("转发任务转化不存在: queue_id=%s", task.id)
            return

        click_association = None
        if conversion.click_id:
            click_association = await ClickAssociator.associate(conversion.click_id, db)

        previous_log = (
            await db.execute(
                _latest_forward_log_query(
                    task.conversion_id, publisher_id=task.publisher_id, product_id=task.product_id
                )
            )
        ).scalars().first()
        previous_log_id = previous_log.id if previous_log else 0

        try:
            if task.publisher_id:
                await PostbackForwarder.forward_to_publisher(
                    conversion, db, click_association=click_association, target_publisher_id=task.publisher_id
                )
            elif task.product_id:
                await PostbackForwarder.forward_to_product(
                    conversion, db, click_association=click_association, target_product_id=task.product_id
                )
            else:
                logger.warning("转发任务缺少 publisher_id/product_id: queue_id=%s", task.id)
                await _delete_owned_forward_task(db, task.id, lease_token)
                return

            latest_log = (
                await db.execute(
                    _latest_forward_log_query(
                        task.conversion_id, publisher_id=task.publisher_id, product_id=task.product_id
                    )
                )
            ).scalars().first()
            if latest_log and latest_log.id > previous_log_id and latest_log.success:
                deleted = await _delete_owned_forward_task(db, task.id, lease_token)
                if deleted:
                    logger.info("转发重试成功: queue_id=%s", task.id)
                else:
                    logger.warning("转发成功但租约已失效，队列状态未修改：queue_id=%s", task.id)
            else:
                await _schedule_or_drop_retry(db, task, lease_token)
        except Exception as forward_err:
            logger.error("转发重试执行失败：queue_id=%s error_type=%s", task.id, type(forward_err).__name__)
            await _schedule_or_drop_retry(db, task, lease_token)
    except Exception as exc:
        logger.error("处理单条转发任务失败：error_type=%s", type(exc).__name__)
        await db.rollback()


async def _schedule_or_drop_retry(db: AsyncSession, task: PostbackForwardQueue, lease_token: str) -> bool:
    """仅当前有效租约可安排退避或移除超限任务。"""
    db_now = get_app_now_sql_expression()
    owned = and_(
        PostbackForwardQueue.id == task.id,
        PostbackForwardQueue.lease_token == lease_token,
        PostbackForwardQueue.lease_expires_at > db_now,
    )
    if task.retry_count >= MAX_RETRIES:
        result = await db.execute(delete(PostbackForwardQueue).where(owned))
        await db.commit()
        if result.rowcount == 1:
            logger.warning("转发任务超过重试上限: queue_id=%s", task.id)
            return True
        return False
    delay = RETRY_DELAYS[min(task.retry_count, len(RETRY_DELAYS) - 1)]
    result = await db.execute(
        update(PostbackForwardQueue)
        .where(owned)
        .values(
            retry_count=PostbackForwardQueue.retry_count + 1,
            next_retry_time=get_app_now_sql_expression(delay),
            lease_token=None,
            lease_expires_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if result.rowcount != 1:
        logger.warning("租约已失效，拒绝覆盖新 Worker 的队列状态：queue_id=%s", task.id)
        return False
    logger.info("转发重试已推迟 (%s/%s): queue_id=%s delay=%ss", task.retry_count + 1, MAX_RETRIES, task.id, delay)
    return True
