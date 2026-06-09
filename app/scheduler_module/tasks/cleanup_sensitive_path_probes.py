"""
敏感路径探测日志清理定时任务。

功能说明：
- 删除 SensitivePathProbeLog 中超过保留天数的记录
- 保留天数默认取自 SENSITIVE_PATH_PROBE_RETENTION_DAYS

在系统中的位置：
- 由敏感路径防护中间件写入日志，本任务负责回收

注意事项：
1. retention_days 可入参覆盖，便于测试环境快速清空
2. 与安全防护中间件配置同步调整，避免磁盘与表无限增长
"""
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

# 与调度器注册名一致，用于日志与任务结果存储
TASK_NAME = "清理敏感路径拦截日志"


async def cleanup_sensitive_path_probe_logs(
        retention_days: int | None = None,
        db: AsyncSession | None = None
) -> dict:
    """
    清理过期的敏感路径拦截日志。

    删除 created_at 早于「当前应用时间 − retention_days」的所有记录，
    提交后返回删除条数及截止时间点等信息。

    参数:
        retention_days: 保留最近 N 天；为 None 时使用 settings.SENSITIVE_PATH_PROBE_RETENTION_DAYS
        db: 可选外部会话；传入时由调用方管理生命周期，未传入则本函数自建并关闭

    返回:
        包含 deleted_count、retention_days、cutoff、message 的字典

    异常:
        删除或提交失败时回滚、记录错误并重新抛出
    """
    # ---------- 计算清理截止时间 ----------
    days = retention_days or int(settings.SENSITIVE_PATH_PROBE_RETENTION_DAYS)
    cutoff = get_app_now_naive() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    log_task_start(TASK_NAME, f"开始清理 {days} 天前日志（<{cutoff_str}）")

    # ---------- 数据库会话：支持外部注入或自建 ----------
    use_external_db = db is not None
    if not use_external_db:
        db = AsyncSessionLocal()
    try:
        # 批量 DELETE，rowcount 为实际删除行数
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
        # 仅在本函数创建的会话需要显式关闭
        if not use_external_db:
            await db.close()


__all__ = ["cleanup_sensitive_path_probe_logs", "get_task_result"]
