"""
CPL 系统定时任务模块。

功能说明：
- 当前包含每日 Cap 计数重置：UTC 零点将各产品/渠道当日转化上限计数归零
- 调用 ``app.core.cap.reset_daily_caps``

在系统中的位置：
- 由 RESET_DAILY_CAPS_TASK_NAME 在每天 00:00 UTC 触发

注意事项：
1. Cap 重置时间与业务统计时区（北京）可能不同，报表须标注 UTC 边界
2. 重置失败会导致当日 Cap 不准，应配置告警
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
    重置每日 Cap 计数任务。

    调用 core.cap.reset_daily_caps 更新数据库中的当日计数；
    成功或失败均写入 task_result_store，并记录耗时便于运维排查。

    建议调度: 每天 00:00 UTC 执行一次。

    异常:
        重置失败时写入失败摘要后重新抛出，由调度器捕获
    """
    logger.info("开始执行每日Cap重置任务...")
    start_time = datetime.now(timezone.utc)

    try:
        async with AsyncSessionLocal() as db:
            # ---------- Cap 计数归零（业务逻辑在 core.cap） ----------
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
