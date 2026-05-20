"""
CPL 系统定时任务
"""
import logging
from datetime import datetime, timezone
from app.core.cap import reset_daily_caps
from app.core.database import AsyncSessionLocal
from app.scheduler_module.task_names import RESET_DAILY_CAPS_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result

logger = logging.getLogger(__name__)


async def reset_daily_caps_task():
    """
    重置每日 Cap 计数任务
    建议每天 00:00 UTC 执行
    """
    logger.info("开始执行每日Cap重置任务...")
    start_time = datetime.now(timezone.utc)

    try:
        async with AsyncSessionLocal() as db:
            await reset_daily_caps(db)
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            msg = f"执行成功: 每日Cap重置（耗时: {round(duration, 2)}秒）"
            set_task_result(RESET_DAILY_CAPS_TASK_NAME, msg)
            logger.debug(msg)
    except Exception as e:
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        set_task_result(
            RESET_DAILY_CAPS_TASK_NAME,
            f"执行失败（耗时: {round(duration, 2)}秒）: {str(e)}",
        )
        logger.error(f"每日Cap重置任务执行失败: {str(e)}", exc_info=True)
        raise
