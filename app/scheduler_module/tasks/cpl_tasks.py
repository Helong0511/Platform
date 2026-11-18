"""
CPL 系统定时任务模块。

功能说明：
- 当前包含每日 Cap 计数重置：业务时区零点将各产品/渠道当日转化上限计数归零
- 调用 ``app.core.cap.reset_daily_caps``

在系统中的位置：
- 由 RESET_DAILY_CAPS_TASK_NAME 在每天 00:00（调度器配置时区，默认 Asia/Shanghai） 触发

注意事项：
1. Cap 重置使用调度器配置时区（默认 Asia/Shanghai），须与业务统计日界保持一致
2. 重置失败会导致当日 Cap 不准，应配置告警
"""
import logging
from datetime import datetime, timezone
from app.core.cap import reset_daily_caps
from app.core.cap.cap_sync import CapSynchronizer
from app.core.database import AsyncSessionLocal
from app.scheduler_module.task_names import RESET_DAILY_CAPS_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result

logger = logging.getLogger(__name__)


async def reset_daily_caps_task():
    """
    重置每日 Cap 计数任务。

    调用 core.cap.reset_daily_caps 更新数据库中的当日计数；
    成功或失败均写入 task_result_store，并记录耗时便于运维排查。

    建议调度: 每天 00:00（调度器配置时区，默认 Asia/Shanghai） 执行一次。

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


CAP_SYNC_TASK_NAME = "Cap计数同步"


async def cap_sync_task():
    """将 Redis Cap 计数同步到数据库。"""
    logger.info("开始执行 Cap 计数同步任务...")
    try:
        async with AsyncSessionLocal() as db:
            synchronizer = CapSynchronizer(db)
            stats = await synchronizer.sync_all_active_caps()
            failed = stats.get("failed", 0)
            skipped = stats.get("skipped", 0)
            if failed:
                raise RuntimeError(
                    f"Cap 同步批次失败并已回滚：failed={failed}"
                )
            msg = (
                f"执行完成: success={stats.get('success', 0)} "
                f"skipped_missing_redis_key={skipped} failed=0"
            )
            set_task_result(CAP_SYNC_TASK_NAME, msg)
            if skipped:
                # Redis key 缺失表示真实计数未知；任务虽然没有发生 DB 写入失败，
                # 但本轮并未完整同步，必须在调度日志中显式暴露为需关注状态。
                logger.warning("Cap 同步部分完成，存在未知计数快照：%s", msg)
            else:
                logger.info(msg)
    except Exception as e:
        set_task_result(CAP_SYNC_TASK_NAME, f"执行失败: {str(e)}")
        logger.error(f"Cap 计数同步任务失败: {e}", exc_info=True)
        raise
