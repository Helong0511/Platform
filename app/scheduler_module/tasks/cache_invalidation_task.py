"""广告数据查询缓存失效 Outbox 定时任务。"""
import logging
from datetime import datetime, timezone

from app.scheduler_module.task_names import AD_DATA_CACHE_INVALIDATION_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.services.cache_invalidation_outbox_worker import process_cache_invalidation_outbox

logger = logging.getLogger(__name__)


async def process_ad_data_cache_invalidation_task():
    """每分钟处理持久化失效事件；Redis 未确认共享失效时保留重试。"""
    started = datetime.now(timezone.utc)
    try:
        stats = await process_cache_invalidation_outbox(batch_size=5)
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        message = (
            f"执行完成：claimed={stats['claimed']} success={stats['success']} "
            f"retryable={stats['retryable']} failed={stats['failed']} "
            f"lease_lost={stats['lease_lost']} duration={duration:.2f}s"
        )
        set_task_result(AD_DATA_CACHE_INVALIDATION_TASK_NAME, message)
        if stats["retryable"] or stats["failed"] or stats["lease_lost"]:
            logger.warning("广告数据缓存失效 Outbox 存在待处理项：%s", message)
        else:
            logger.info(message)
        return stats
    except Exception as exc:
        set_task_result(
            AD_DATA_CACHE_INVALIDATION_TASK_NAME,
            f"执行失败：{type(exc).__name__}",
        )
        logger.error(
            "广告数据缓存失效 Outbox 任务失败：error_type=%s",
            type(exc).__name__,
        )
        raise
