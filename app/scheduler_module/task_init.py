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


async def init_scheduled_tasks_in_db() -> None:
    """
    初始化定时任务到数据库
    检查 task_config.py 中定义的所有任务，如果数据库中不存在则自动添加
    
    这个函数应该在应用启动时调用，确保所有配置的任务都在数据库中有记录
    
    注意：在多进程环境下，多个进程可能同时执行此函数，因此需要处理并发插入冲突
    """
    logger.info("开始检查并初始化定时任务到数据库...")

    async with AsyncSessionLocal() as db:
        try:
            added_count = 0
            existing_count = 0
            updated_count = 0

            for config_key, config in TASK_CONFIGS.items():
                task_name = config["task_name"]
                task_module = config["task_module"]
                task_function = config["task_function"]

                # 构建函数路径
                function_path = f"{task_module}.{task_function}"

                # 从配置中获取 cron_expression 和 description（如果配置了）
                cron_expression = config.get("cron_expression", "0 * * * *")  # 默认每小时
                description = config.get("description", f"自动创建的任务: {task_name}")

                # 检查任务是否已存在（使用行锁防止并发问题）
                result = await db.execute(
                    select(ScheduledTask)
                    .where(ScheduledTask.task_name == task_name)
                    .with_for_update(skip_locked=True)  # 跳过被其他事务锁定的记录
                )
                existing_task = result.scalar_one_or_none()

                if existing_task:
                    # 任务已存在，更新配置（如果不同）
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
                        logger.info(f"更新任务 '{task_name}' 的配置")
                    else:
                        existing_count += 1
                        logger.debug(f"任务 '{task_name}' 已存在，跳过")

                    # 立即提交这个任务的更新（避免长时间锁定）
                    try:
                        await db.commit()
                    except Exception as e:
                        await db.rollback()
                        logger.warning(f"更新任务 '{task_name}' 失败: {e}")
                else:
                    # 任务不存在，尝试创建新任务
                    try:
                        new_task = ScheduledTask(
                            task_name=task_name,
                            cron_expression=cron_expression,
                            description=description,
                            function_path=function_path,
                            is_active=True,  # 默认启用
                            is_running=False,
                            run_count=0,
                            success_count=0,
                            error_count=0,
                        )

                        db.add(new_task)
                        # 立即提交（避免批量提交时的并发冲突）
                        await db.commit()
                        added_count += 1
                        logger.info(
                            f"添加新任务到数据库: '{task_name}' "
                            f"(Cron: {cron_expression}, 描述: {description})"
                        )
                    except Exception as e:
                        # 如果是因为唯一约束冲突（并发插入），尝试更新
                        await db.rollback()
                        if "Duplicate entry" in str(e) or "1062" in str(e):
                            # 并发插入冲突，重新查询并更新
                            logger.debug(
                                f"任务 '{task_name}' 并发插入冲突，尝试更新: {e}"
                            )
                            result = await db.execute(
                                select(ScheduledTask).where(ScheduledTask.task_name == task_name)
                            )
                            existing_task = result.scalar_one_or_none()
                            if existing_task:
                                # 更新配置
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
                                    await db.commit()
                                    updated_count += 1
                                    logger.info(f"更新任务 '{task_name}' 的配置（并发冲突后）")
                                else:
                                    existing_count += 1
                                    logger.debug(f"任务 '{task_name}' 已存在（并发冲突后）")
                            else:
                                # 如果还是找不到，记录错误但不抛出异常
                                logger.warning(
                                    f"任务 '{task_name}' 插入失败且查询不到: {e}"
                                )
                        else:
                            # 其他错误，记录但不中断整个初始化过程
                            logger.error(
                                f"添加任务 '{task_name}' 失败: {e}",
                                exc_info=True
                            )

            logger.info(
                f"定时任务数据库初始化完成: "
                f"新增 {added_count} 个任务, "
                f"更新 {updated_count} 个任务, "
                f"已存在 {existing_count} 个任务, "
                f"总计 {len(TASK_CONFIGS)} 个任务"
            )

        except Exception as e:
            await db.rollback()
            logger.error(f"初始化定时任务到数据库失败: {e}", exc_info=True)
            # 不抛出异常，允许应用继续启动（任务可能已经存在）
            logger.warning("任务初始化失败，但允许应用继续启动...")


async def sync_task_configs_to_db() -> None:
    """
    同步任务配置到数据库
    确保 task_config.py 中的所有任务都在数据库中有记录，并且函数路径是最新的
    
    这个函数可以在应用启动时调用，或者在管理界面中手动触发
    """
    await init_scheduled_tasks_in_db()
