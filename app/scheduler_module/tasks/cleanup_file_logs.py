"""
文件日志超期清理定时任务。

功能说明：
- 清理 logs/ 下超期轮转备份与 archive 内超期 gzip
- 可选归档（gzip）、gunicorn 溢出轮转、磁盘软/硬限制守卫
- 与 DB 审计日志清理（cleanup_old_audit_logs）相互独立

由 CLEANUP_FILE_LOGS_TASK_NAME 调度触发。
"""
from __future__ import annotations

import logging

from app.core.log_file_cleanup import run_file_log_cleanup
from app.scheduler_module.task_names import CLEANUP_FILE_LOGS_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.task_utils import log_task_error, log_task_result, log_task_start

logger = logging.getLogger(__name__)

TASK_NAME = CLEANUP_FILE_LOGS_TASK_NAME


async def cleanup_file_logs() -> dict:
    """
    执行文件日志超期清理。

    Returns:
        清理统计字典（含 message）
    """
    log_task_start(TASK_NAME, "开始清理超期文件日志与归档")
    try:
        result = run_file_log_cleanup()
        msg = result.get("message") or "清理完成"
        if result.get("skipped"):
            log_task_result(TASK_NAME, msg, level="warning")
        else:
            level = "warning" if result.get("errors") or result.get("hard_limit_hit") else "info"
            log_task_result(TASK_NAME, msg, level=level)
        set_task_result(TASK_NAME, msg)
        return result
    except Exception as exc:
        err = f"清理失败: {exc}"
        log_task_error(TASK_NAME, err, exc_info=True)
        set_task_result(TASK_NAME, err)
        raise


__all__ = ["cleanup_file_logs", "get_task_result"]
