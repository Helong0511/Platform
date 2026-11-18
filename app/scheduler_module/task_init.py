"""
定时任务数据库初始化工具。

功能说明：
- 启动时将 ``task_config.py`` 中定义的任务同步到 ``scheduled_tasks`` 表
- 新增配置自动 INSERT，已存在则可选更新 Cron/描述

在系统中的位置：
- 由 ``app.main`` lifespan 在**每次应用启动**时调用（与 ENABLE_SCHEDULER 无关）
- APScheduler 注册/启动仍仅在 ``should_run_scheduler()`` 为真时执行

注意事项：
1. 仅以 task_config 为真相源，手工改 DB 可能在下次 init 被覆盖
2. 禁用任务用 is_active=False，勿直接删行以免丢失执行历史
"""
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.models import ScheduledTask
from app.scheduler_module.task_config import TASK_CONFIGS

logger = logging.getLogger(__name__)


def _is_retryable_task_sync_conflict(exc: Exception) -> bool:
    """识别唯一键竞争、MySQL 死锁/锁等待超时等可安全整批重试的冲突。"""
    original = getattr(exc, "orig", exc)
    args = getattr(original, "args", ())
    if args and args[0] in (1062, 1205, 1213):
        # 1062 duplicate key；1205 lock wait timeout；1213 deadlock victim。
        return True
    message = str(original).lower()
    return (
        "duplicate entry" in message
        or "unique constraint failed" in message
        or "duplicate key value violates unique constraint" in message
        or "database is locked" in message
    )


async def init_scheduled_tasks_in_db() -> None:
    """
    将 TASK_CONFIGS 原子同步到 scheduled_tasks。

    多 Worker 同时启动时，唯一键竞争会回滚整个批次并重新读取数据库；
    任意非重复键错误都会向上传播，禁止把部分同步伪装成成功。
    """
    logger.info("开始检查并初始化定时任务到数据库...")

    # 配置本身有重复 task_name 时，数据库唯一键无法表达预期来源，启动前直接拒绝。
    configured_names = [
        config.get("task_name")
        for config in TASK_CONFIGS.values()
    ]
    if any(not isinstance(name, str) or not name.strip() for name in configured_names):
        raise ValueError("定时任务配置包含空 task_name")
    if len(configured_names) != len(set(configured_names)):
        raise ValueError("定时任务配置包含重复 task_name")

    max_attempts = 3
    async with AsyncSessionLocal() as db:
        for attempt in range(1, max_attempts + 1):
            added_count = 0
            existing_count = 0
            updated_count = 0
            try:
                for config in TASK_CONFIGS.values():
                    task_name = config["task_name"]
                    function_path = f"{config['task_module']}.{config['task_function']}"
                    cron_expression = config.get("cron_expression", "0 * * * *")
                    description = config.get("description", f"自动创建的任务: {task_name}")

                    # 不使用 SKIP LOCKED：被其它 Worker 锁定的任务不能被误判为不存在。
                    result = await db.execute(
                        select(ScheduledTask)
                        .where(ScheduledTask.task_name == task_name)
                        .with_for_update()
                    )
                    existing_task = result.scalar_one_or_none()

                    if existing_task is None:
                        db.add(
                            ScheduledTask(
                                task_name=task_name,
                                cron_expression=cron_expression,
                                description=description,
                                function_path=function_path,
                                is_active=True,
                                is_running=False,
                                run_count=0,
                                success_count=0,
                                error_count=0,
                            )
                        )
                        added_count += 1
                        continue

                    updated = False
                    if existing_task.function_path != function_path:
                        existing_task.function_path = function_path
                        updated = True
                    if existing_task.cron_expression != cron_expression:
                        existing_task.cron_expression = cron_expression
                        updated = True
                    if existing_task.description != description:
                        existing_task.description = description
                        updated = True

                    if updated:
                        updated_count += 1
                    else:
                        existing_count += 1

                # 一个事务提交整批配置，避免前半批成功、后半批失败的隐式部分状态。
                await db.commit()
                logger.info(
                    "定时任务数据库同步完成: 新增 %s 个、更新 %s 个、未变化 %s 个、总计 %s 个",
                    added_count,
                    updated_count,
                    existing_count,
                    len(TASK_CONFIGS),
                )
                return
            except Exception as exc:
                await db.rollback()
                if _is_retryable_task_sync_conflict(exc) and attempt < max_attempts:
                    logger.info(
                        "定时任务同步遇到唯一键/锁竞争，将回滚整批并重新读取（第 %s/%s 次）",
                        attempt,
                        max_attempts,
                    )
                    continue
                logger.error(
                    "定时任务数据库同步失败：exception_type=%s attempt=%s",
                    type(exc).__name__,
                    attempt,
                )
                raise

    raise RuntimeError("定时任务配置同步在重试后仍未完成")


async def sync_task_configs_to_db() -> None:
    """
    同步任务配置到数据库
    确保 task_config.py 中的所有任务都在数据库中有记录，并且函数路径是最新的
    
    这个函数可以在应用启动时调用，或者在管理界面中手动触发
    """
    await init_scheduled_tasks_in_db()
