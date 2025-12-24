"""
CPL 系统定时任务
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.cap import reset_daily_caps
from app.scheduler_module.task_names import RESET_DAILY_CAPS_TASK_NAME

logger = logging.getLogger(__name__)

# 任务执行结果存储（用于定时任务系统）
# 格式化为字符串，用于保存到数据库的last_error字段
_task_result_message: Optional[str] = None


async def reset_daily_caps_task():
    """
    重置每日 Cap 计数任务
    建议每天 00:00 UTC 执行
    """
    global _task_result_message
    
    logger.info("开始执行每日Cap重置任务...")
    start_time = datetime.now(timezone.utc)
    
    try:
        async with AsyncSessionLocal() as db:
            await reset_daily_caps(db)
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            _task_result_message = f"每日Cap重置任务执行成功（耗时: {round(duration, 2)}秒）"
            logger.info(_task_result_message)
    except Exception as e:
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        _task_result_message = f"执行失败（耗时: {round(duration, 2)}秒）: {str(e)}"
        logger.error(f"每日Cap重置任务执行失败: {str(e)}", exc_info=True)
        raise


def get_task_result(task_name: str) -> Optional[str]:
    """
    获取任务执行结果（用于定时任务系统）
    返回字符串格式的结果，用于保存到数据库
    
    Args:
        task_name: 任务名称（用于兼容任务结果注册表接口）
        
    Returns:
        任务执行结果字符串，如果不存在返回 None
    """
    return _task_result_message
