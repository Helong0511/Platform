"""第三方 Postback Report Outbox 定时恢复任务。"""
import logging
from datetime import datetime, timezone

from app.scheduler_module.task_names import THIRD_PARTY_REPORT_OUTBOX_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.services.third_party_report_outbox import process_postback_report_outbox

logger = logging.getLogger(__name__)


async def process_third_party_report_outbox_task():
    """每分钟消费到期事件；进程重启后由数据库 Outbox 自动恢复。"""
    started = datetime.now(timezone.utc)
    try:
        stats = await process_postback_report_outbox(batch_size=20)
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        message = (
            f"执行完成：selected={stats['selected']} success={stats['success']} "
            f"retryable={stats['retryable']} failed={stats['failed']} "
            f"duration={duration:.2f}s"
        )
        set_task_result(THIRD_PARTY_REPORT_OUTBOX_TASK_NAME, message)
        if stats["retryable"] or stats["failed"]:
            logger.warning("第三方 Report Outbox 存在待重试/失败事件：%s", message)
        else:
            logger.info(message)
        return stats
    except Exception as exc:
        set_task_result(THIRD_PARTY_REPORT_OUTBOX_TASK_NAME, f"执行失败：{exc}")
        logger.error("第三方 Report Outbox 恢复任务失败", exc_info=True)
        raise
