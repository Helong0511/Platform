"""短链接热点缓存失效 Outbox 定时任务。"""
import logging
from datetime import datetime, timezone

from app.scheduler_module.task_names import SHORT_LINK_CACHE_INVALIDATION_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.services.short_link_cache_invalidation_outbox_worker import (
    process_short_link_cache_invalidation_outbox,
)

logger = logging.getLogger(__name__)


async def process_short_link_cache_invalidation_task():
    """定期消费短链接缓存失效事件，Redis 故障时由 Outbox 自动重试。"""
    started = datetime.now(timezone.utc)
    try:
        stats = await process_short_link_cache_invalidation_outbox(batch_size=100)
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        message = (
            f"执行完成：claimed={stats['claimed']} success={stats['success']} "
            f"retryable={stats['retryable']} failed={stats['failed']} "
            f"lease_lost={stats['lease_lost']} duration={duration:.2f}s"
        )
        set_task_result(SHORT_LINK_CACHE_INVALIDATION_TASK_NAME, message)
        if stats["retryable"] or stats["failed"] or stats["lease_lost"]:
            logger.warning("短链接缓存失效 Outbox 存在待处理项：%s", message)
        else:
            logger.info(message)
        return stats
    except Exception as exc:
        set_task_result(
            SHORT_LINK_CACHE_INVALIDATION_TASK_NAME,
            f"执行失败：{type(exc).__name__}",
        )
        logger.error(
            "短链接缓存失效 Outbox 任务失败：error_type=%s",
            type(exc).__name__,
        )
        raise
