"""敏感路径拦截日志清理任务。"""
import logging
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.models import SensitivePathProbeLog
from app.scheduler_module.task_result_store import set_task_result, get_task_result
from app.scheduler_module.task_utils import log_task_start, log_task_result, log_task_error

logger = logging.getLogger(__name__)
TASK_NAME = "清理敏感路径拦截日志"


async def cleanup_sensitive_path_probe_logs(
        retention_days: int | None = None,
        db: AsyncSession | None = None
) -> dict:
    """
    清理过期敏感路径拦截日志。
    """
    days = retention_days or int(settings.SENSITIVE_PATH_PROBE_RETENTION_DAYS)
    cutoff = get_app_now_naive() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    log_task_start(TASK_NAME, f"开始清理 {days} 天前日志（<{cutoff_str}）")

    use_external_db = db is not None
    if not use_external_db:
        db = AsyncSessionLocal()
    try:
        result = await db.execute(
            delete(SensitivePathProbeLog).where(SensitivePathProbeLog.created_at < cutoff)
        )
        deleted_count = int(result.rowcount or 0)
        await db.commit()
        msg = f"清理完成：删除 {deleted_count} 条，保留最近 {days} 天"
        log_task_result(TASK_NAME, msg, level="info")
        set_task_result(TASK_NAME, msg)
        return {
            "deleted_count": deleted_count,
            "retention_days": days,
            "cutoff": cutoff_str,
            "message": msg,
        }
    except Exception as exc:
        await db.rollback()
        err = f"清理失败: {exc}"
        log_task_error(TASK_NAME, err, exc_info=True)
        set_task_result(TASK_NAME, err)
        raise
    finally:
        if not use_external_db:
            await db.close()


__all__ = ["cleanup_sensitive_path_probe_logs", "get_task_result"]
