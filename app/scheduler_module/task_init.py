"""
定时任务数据库初始化工具
自动检查并添加配置文件中定义的任务到数据库
所有配置都在 task_config.py 中统一管理
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
    """
    logger.info("开始检查并初始化定时任务到数据库...")
    
    async with AsyncSessionLocal() as db:
        try:
            added_count = 0
            existing_count = 0
            
            for config_key, config in TASK_CONFIGS.items():
                task_name = config["task_name"]
                task_module = config["task_module"]
                task_function = config["task_function"]
                
                # 构建函数路径
                function_path = f"{task_module}.{task_function}"
                
                # 检查任务是否已存在
                result = await db.execute(
                    select(ScheduledTask).where(ScheduledTask.task_name == task_name)
                )
                existing_task = result.scalar_one_or_none()
                
                if existing_task:
                    # 任务已存在，更新函数路径（如果不同）
                    if existing_task.function_path != function_path:
                        existing_task.function_path = function_path
                        logger.info(f"更新任务 '{task_name}' 的函数路径: {function_path}")
                    existing_count += 1
                    logger.debug(f"任务 '{task_name}' 已存在，跳过")
                else:
                    # 任务不存在，创建新任务
                    # 从配置中获取 cron_expression 和 description（如果配置了）
                    cron_expression = config.get("cron_expression", "0 * * * *")  # 默认每小时
                    description = config.get("description", f"自动创建的任务: {task_name}")
                    
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
                    added_count += 1
                    logger.info(
                        f"添加新任务到数据库: '{task_name}' "
                        f"(Cron: {cron_expression}, 描述: {description})"
                    )
            
            # 提交所有更改
            await db.commit()
            
            logger.info(
                f"定时任务数据库初始化完成: "
                f"新增 {added_count} 个任务, "
                f"已存在 {existing_count} 个任务, "
                f"总计 {len(TASK_CONFIGS)} 个任务"
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"初始化定时任务到数据库失败: {e}", exc_info=True)
            raise


async def sync_task_configs_to_db() -> None:
    """
    同步任务配置到数据库
    确保 task_config.py 中的所有任务都在数据库中有记录，并且函数路径是最新的
    
    这个函数可以在应用启动时调用，或者在管理界面中手动触发
    """
    await init_scheduled_tasks_in_db()

