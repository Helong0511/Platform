"""Cap Reservation 崩溃恢复调度任务。"""
import logging
from datetime import datetime, timezone

from app.scheduler_module.task_names import CAP_RESERVATION_RECOVERY_TASK_NAME
# 该 getter 由 task_config.result_getter_module 动态按模块属性加载，需显式导出。
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.services.cap_reservation_recovery import (
    get_cap_reservation_recovery_status,
    recover_cap_reservations,
)

logger = logging.getLogger(__name__)


async def cap_reservation_recovery_task():
    """每分钟恢复可确定的孤儿预留；未知 Redis 状态只告警，不执行猜测性 DECR。"""
    started = datetime.now(timezone.utc)
    try:
        stats = await recover_cap_reservations()
        backlog = await get_cap_reservation_recovery_status()
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        message = (
            f"执行完成：claimed={stats['claimed']} committed={stats['committed']} "
            f"rolled_back={stats['rolled_back']} "
            f"needs_reconciliation={stats['needs_reconciliation']} "
            f"tokens_cleaned={stats['tokens_cleaned']} "
            f"cleanup_pending={stats['cleanup_pending']} "
            f"backlog_prepared={backlog['pending_prepared']} "
            f"backlog_reserved={backlog['pending_reserved']} "
            f"backlog_needs_reconciliation={backlog['needs_reconciliation']} "
            f"backlog_token_cleanup={backlog['committed_token_cleanup_pending']} "
            f"oldest_pending_seconds={backlog['oldest_pending_seconds']} "
            f"failed={stats['failed']} duration={duration:.2f}s"
        )
        set_task_result(CAP_RESERVATION_RECOVERY_TASK_NAME, message)
        if (
            stats["needs_reconciliation"]
            or stats["cleanup_pending"]
            or stats["failed"]
            or backlog["needs_reconciliation"]
            or backlog["committed_token_cleanup_pending"]
            or backlog["oldest_pending_seconds"] > 600
        ):
            logger.warning("Cap Reservation 恢复任务存在待对账项：%s", message)
        else:
            logger.info(message)
        return stats
    except Exception as exc:
        set_task_result(CAP_RESERVATION_RECOVERY_TASK_NAME, f"执行失败：{exc}")
        logger.error("Cap Reservation 崩溃恢复任务失败", exc_info=True)
        raise
