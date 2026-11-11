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
            f"exhausted={stats['exhausted']} duration={duration:.2f}s"
        )
        set_task_result(THIRD_PARTY_REPORT_OUTBOX_TASK_NAME, message)
        if stats["retryable"] or stats["failed"] or stats["exhausted"]:
            logger.warning("第三方 Report Outbox 存在待重试/失败事件：%s", message)
        else:
            logger.info(message)
        return stats
    except Exception as exc:
        set_task_result(
            THIRD_PARTY_REPORT_OUTBOX_TASK_NAME,
            f"执行失败：{type(exc).__name__}",
        )
        logger.error(
            "第三方 Report Outbox 恢复任务失败：error_type=%s",
            type(exc).__name__,
        )
        raise


async def scrub_third_party_report_pii_task():
    """每天执行一次；保留天数未获批准（配置为 0）时安全跳过。"""
    from app.services.third_party_report_pii_retention import (
        scrub_expired_postback_forward_log_pii,
        scrub_expired_third_party_report_pii,
    )
    from app.scheduler_module.task_names import (
        THIRD_PARTY_REPORT_PII_RETENTION_TASK_NAME,
    )

    try:
        stats = await scrub_expired_third_party_report_pii(batch_size=200)
        forward_stats = await scrub_expired_postback_forward_log_pii(batch_size=200)
        message = (
            f"执行完成：report_scrubbed={stats['scrubbed']} "
            f"forward_log_scrubbed={forward_stats['scrubbed']} "
            f"enabled={stats['enabled']} retention_days={stats['retention_days']}"
        )
        set_task_result(THIRD_PARTY_REPORT_PII_RETENTION_TASK_NAME, message)
        logger.info("第三方上报及下游转发日志 PII 生命周期任务：%s", message)
        return {**stats, "postback_forward_logs": forward_stats}
    except Exception as exc:
        set_task_result(
            THIRD_PARTY_REPORT_PII_RETENTION_TASK_NAME,
            f"执行失败：{type(exc).__name__}",
        )
        logger.error(
            "第三方上报 PII 生命周期任务失败：error_type=%s",
            type(exc).__name__,
        )
        raise
