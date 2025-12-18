"""
CPL 系统定时任务
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.cap import reset_daily_caps

logger = logging.getLogger(__name__)

# 任务执行结果存储（用于定时任务系统）
_task_result = {
    "last_run_time": None,
    "last_run_status": None,
    "last_run_message": None,
    "run_count": 0,
    "success_count": 0,
    "error_count": 0
}


async def reset_daily_caps_task():
    """
    重置每日 Cap 计数任务
    建议每天 00:00 UTC 执行
    """
    global _task_result
    
    logger.info("开始执行每日Cap重置任务...")
    _task_result["last_run_time"] = datetime.now(timezone.utc)
    _task_result["run_count"] += 1
    
    try:
        async with AsyncSessionLocal() as db:
            await reset_daily_caps(db)
            _task_result["last_run_status"] = "success"
            _task_result["last_run_message"] = "每日Cap重置任务执行成功"
            _task_result["success_count"] += 1
            logger.info("每日Cap重置任务执行成功")
    except Exception as e:
        _task_result["last_run_status"] = "error"
        _task_result["last_run_message"] = f"执行失败: {str(e)}"
        _task_result["error_count"] += 1
        logger.error(f"每日Cap重置任务执行失败: {str(e)}", exc_info=True)
        raise


def get_task_result() -> dict:
    """
    获取任务执行结果（用于定时任务系统）
    """
    return _task_result.copy()
