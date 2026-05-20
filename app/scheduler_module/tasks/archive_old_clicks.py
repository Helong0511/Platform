"""
点击记录归档任务（薄任务层，逻辑在 ClicksArchiveService）。
"""
import logging

from app.core.database import AsyncSessionLocal
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    format_result_summary,
    log_task_error,
    log_task_result,
    log_task_start,
)
from app.services.tracking.clicks_archive_service import clicks_archive_service

logger = logging.getLogger(__name__)


async def archive_old_clicks(days: int = 90) -> dict:
    """归档指定天数之前的点击记录到 clicks_archive。"""
    task_name = "点击记录归档"
    log_task_start(task_name, f"归档 {days} 天前的点击记录")

    async with AsyncSessionLocal() as db:
        try:
            result = await clicks_archive_service.archive_old_clicks(db, days=days)

            if result.get("skipped"):
                msg = result.get("message", "已跳过归档")
                log_task_result(task_name, msg, level="warning")
                set_task_result(task_name, f"执行成功: {msg}")
                return result

            if result["archived_count"] == 0 and result["deleted_count"] == 0:
                msg = result.get("message", "没有需要归档的数据")
                log_task_result(task_name, msg, level="warning")
                set_task_result(task_name, f"执行成功: {msg}")
                return result

            summary = format_result_summary(
                archived=result["archived_count"],
                deleted=result["deleted_count"],
            )
            log_task_result(task_name, summary, level="warning")
            set_task_result(
                task_name,
                f"执行成功: 归档 {result['archived_count']} 条, "
                f"删除 {result['deleted_count']} 条",
            )
            logger.info(
                "归档完成：归档 %s 条，删除 %s 条",
                result["archived_count"],
                result["deleted_count"],
            )
            return result
        except Exception as e:
            await db.rollback()
            log_task_error(task_name, str(e), exc_info=True)
            set_task_result(task_name, f"执行失败: {str(e)}")
            raise
