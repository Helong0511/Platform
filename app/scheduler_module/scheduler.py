"""
定时任务调度器核心模块。

功能说明：
- 使用 APScheduler AsyncIOScheduler 注册 Cron/Interval 触发器
- ``execute_task_with_lock`` 结合 DB 锁与进程分配器，保证多进程只跑一次
- 任务执行结果写入 task_result_store，并同步 scheduled_tasks 表状态

在系统中的位置：
- 被 ``scheduler_module.__init__`` 导出；启动入口在 ``app.main`` lifespan

注意事项：
1. 任务函数须为 async 或可 await 的协程，阻塞 IO 应放线程池
2. 跳过执行（锁未获取）须记 audit 日志，便于排查「任务未跑」误报
"""
import warnings

# 抑制 APScheduler 的 pkg_resources 弃用警告
# 这是 APScheduler 库内部使用已弃用的 pkg_resources 导致的警告
# 不影响功能，等待库更新修复
warnings.filterwarnings('ignore', message='.*pkg_resources is deprecated.*', category=UserWarning)

import os
import asyncio
import logging
import threading
from datetime import datetime
from typing import Optional, Callable, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from sqlalchemy.future import select

from app.scheduler_module.lock import (
    acquire_task_lock,
    release_task_lock,
    get_current_pid,
    CURRENT_HOST,
    DEFAULT_TIMEOUT_SECONDS,
)
from app.scheduler_module.task_queue import submit_task_to_queue, TaskPriority
from app.scheduler_module.process_allocator import (
    should_execute_in_current_process, register_task_process_assignment
)
from app.scheduler_module.task_utils import (
    log_scheduled_task_failure,
    log_scheduled_task_skip,
    log_scheduled_task_start,
)
from app.scheduler_module.task_registry import (
    auto_register_tasks,
    get_task_function_by_name_or_path
)
from app.scheduler_module.task_result_registry import get_task_result, auto_register_task_results
from app.core.config import settings
from app.core.db_errors import is_database_unreachable_error
from app.core.utils import get_app_now_naive, APP_TIMEZONE
from app.core.database import AsyncSessionLocal
from app.models.models import ScheduledTask
from app.core.audit_log import log_user_action

logger = logging.getLogger(__name__)

# 常量配置
DEFAULT_TIMEZONE = settings.TIMEZONE  # 从配置读取时区
DEFAULT_MISFIRE_GRACE_TIME = 60  # 默认错过执行时间容忍度（秒）

# 全局调度器实例
scheduler: Optional[AsyncIOScheduler] = None
# 线程锁，确保调度器初始化的线程安全
_scheduler_lock = threading.Lock()
# 关闭标志：停服期间拒绝新任务，避免 MySQL 已停后仍触发 cron
_scheduler_shutting_down = False


def is_scheduler_shutting_down() -> bool:
    """调度器是否正在关闭（lifespan 退出或 shutdown_scheduler 调用后）。"""
    return _scheduler_shutting_down


def mark_scheduler_shutting_down() -> None:
    """标记调度器进入关闭流程，后续 cron 触发将直接跳过。"""
    global _scheduler_shutting_down
    _scheduler_shutting_down = True


def get_scheduler() -> AsyncIOScheduler:
    """
    获取调度器实例（线程安全的单例模式）
    
    Returns:
        AsyncIOScheduler: 调度器实例
    """
    global scheduler
    if scheduler is None:
        with _scheduler_lock:
            # 双重检查锁定模式，确保线程安全
            if scheduler is None:
                scheduler = AsyncIOScheduler(
                    jobstores={
                        'default': MemoryJobStore()
                    },
                    executors={
                        'default': AsyncIOExecutor()  # 使用异步执行器，支持 async 函数
                    },
                    job_defaults={
                        'coalesce': True,  # 如果任务被跳过，合并为一次执行
                        'max_instances': 1,  # 同一任务最多1个实例
                        'misfire_grace_time': DEFAULT_MISFIRE_GRACE_TIME  # 错过执行时间后60秒内仍可执行
                    },
                    timezone=DEFAULT_TIMEZONE  # 使用配置的应用时区
                )
                worker_pid = os.getpid()
                logger.info(
                    f"[Worker PID:{worker_pid}] 调度器已初始化（时区: {DEFAULT_TIMEZONE}, 执行器: AsyncIOExecutor）"
                )
    return scheduler


def get_job_next_run_time(job: Any, *, now: Optional[datetime] = None) -> Optional[datetime]:
    """
    安全获取 APScheduler Job 的下次执行时间。

    - 已入调度且正常运行：返回 job.next_run_time
    - 已暂停（next_run_time 为 None）：返回 None，由调用方显示「未计划」
    - pending（尚未入 job store）：用 trigger 推算理论下次执行时间
    """
    if getattr(job, "pending", False):
        trigger = getattr(job, "trigger", None)
        if trigger is None:
            return None
        try:
            ref = now or datetime.now(APP_TIMEZONE)
            return trigger.get_next_fire_time(None, ref)
        except Exception:
            return None

    # 已入 job store：以 next_run_time 为准（None 表示暂停，不做 trigger 回退）
    return getattr(job, "next_run_time", None)


def format_job_next_run_time(
        job: Any,
        *,
        now: Optional[datetime] = None,
        fmt: str = "%Y-%m-%d %H:%M:%S",
) -> str:
    """格式化 Job 下次执行时间；无法获取时返回「未计划」。"""
    next_run_time = get_job_next_run_time(job, now=now)
    if not next_run_time:
        return "未计划"
    try:
        return next_run_time.strftime(fmt)
    except Exception:
        return str(next_run_time)


async def execute_task_with_lock(
        task_name: str,
        task_func: Callable[..., Any],
        skip_process_check: bool = False,  # 新增：是否跳过进程分配检查（用于手动触发）
        *args: Any,
        **kwargs: Any
) -> None:
    """
    执行任务（带锁机制，确保多进程环境下只执行一次）
    通过任务队列管理，避免同一进程同时执行过多任务
    支持跨进程任务分配，根据执行时间分配到不同进程
    
    Args:
        task_name: 任务名称
        task_func: 任务函数（可以是同步或异步函数）
        skip_process_check: 是否跳过进程分配检查（True=手动触发，False=定时触发）
        *args: 任务函数位置参数
        **kwargs: 任务函数关键字参数
    """
    if is_scheduler_shutting_down():
        log_scheduled_task_skip(
            task_name,
            "调度器正在关闭",
            detail=f"pid={os.getpid()} host={CURRENT_HOST}",
        )
        return

    # 如果跳过进程检查（手动触发），直接执行
    if skip_process_check:
        worker_pid = os.getpid()
        logger.info(
            f"[Worker PID:{worker_pid}] 手动触发任务 '{task_name}'，跳过进程分配检查，直接执行"
        )
        # 直接执行，不检查进程分配
        priority = TaskPriority.NORMAL

        async def wrapped_task():
            """手动触发路径：跳过进程分配后直接带锁执行。"""
            await _execute_task_with_lock_internal(task_name, task_func, *args, **kwargs)

        await submit_task_to_queue(
            task_name=task_name,
            task_func=wrapped_task,
            priority=priority
        )
        return

    # 查询任务的cron表达式和运行状态
    db = AsyncSessionLocal()
    try:
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.task_name == task_name)
        )
        task_record = result.scalar_one_or_none()

        # 先检查任务是否正在运行（避免不必要的进程分配检查）
        if task_record and task_record.is_running:
            # 检查是否超时（可能是上次执行异常导致锁未释放）
            if task_record.last_run_time:
                # 确保 last_run_time 是 naive datetime（数据库存储的是北京时间）
                if task_record.last_run_time.tzinfo is None:
                    # 如果数据库返回的是 naive datetime，假设是北京时间
                    last_run_app = task_record.last_run_time
                else:
                    # 如果带时区信息，转换为北京时间（naive）
                    last_run_app = task_record.last_run_time.astimezone(APP_TIMEZONE).replace(tzinfo=None)

                now_app = get_app_now_naive()  # 使用北京时间比较
                elapsed = (now_app - last_run_app).total_seconds()

                if elapsed < DEFAULT_TIMEOUT_SECONDS:
                    log_scheduled_task_skip(
                        task_name,
                        "任务仍在运行中，跳过本次触发",
                        detail=(
                            f"holder_pid={task_record.last_run_pid} "
                            f"holder_host={task_record.last_run_host} "
                            f"elapsed_sec={elapsed:.1f} "
                            f"timeout_sec={DEFAULT_TIMEOUT_SECONDS}"
                        ),
                    )
                    return

        if not task_record or not task_record.cron_expression:
            # 如果没有找到任务记录或没有cron表达式，直接执行
            cron_expression = None
        else:
            cron_expression = task_record.cron_expression
    except Exception as e:
        if is_database_unreachable_error(e):
            log_scheduled_task_skip(
                task_name,
                "数据库不可用",
                detail=str(e),
            )
            return
        logger.warning(f"查询任务信息失败: {e}，将直接执行")
        cron_expression = None
    finally:
        await db.close()

    # 如果有cron表达式，检查是否应该由当前进程执行
    if cron_expression:
        should_execute = await should_execute_in_current_process(
            task_name, cron_expression
        )
        if not should_execute:
            log_scheduled_task_skip(
                task_name,
                "进程分配：应由其他 worker 执行",
                detail=f"current_pid={os.getpid()} host={CURRENT_HOST} cron={cron_expression}",
            )
            return

    # 根据任务名称确定优先级（可以根据实际需求调整）
    # 默认使用 NORMAL 优先级
    priority = TaskPriority.NORMAL

    # 创建包装函数，将实际执行逻辑包装为异步函数
    async def wrapped_task():
        """定时触发路径：经任务队列提交后带分布式锁执行。"""
        await _execute_task_with_lock_internal(task_name, task_func, *args, **kwargs)

    # 将任务提交到队列，队列会管理并发执行
    worker_pid = os.getpid()
    logger.debug(
        f"[Worker PID:{worker_pid}] 任务 '{task_name}' 已分配给当前进程，"
        f"提交到任务队列（优先级: {priority.name}）"
    )

    await submit_task_to_queue(
        task_name=task_name,
        task_func=wrapped_task,
        priority=priority
    )


async def _execute_task_with_lock_internal(
        task_name: str,
        task_func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
) -> None:
    """
    执行任务（内部方法，实际执行逻辑）
    带锁机制，确保多进程环境下只执行一次
    
    Args:
        task_name: 任务名称
        task_func: 任务函数（可以是同步或异步函数）
        *args: 任务函数位置参数
        **kwargs: 任务函数关键字参数
    """
    # 尝试获取锁
    acquired, lock_db = await acquire_task_lock(task_name)
    if not acquired:
        log_scheduled_task_skip(
            task_name,
            "无法获取任务锁",
            detail=f"pid={get_current_pid()} host={CURRENT_HOST}",
        )
        return

    # 确保数据库会话在 finally 中关闭
    task_record = None
    task_id = None
    start_time = get_app_now_naive()  # 使用北京时间记录开始时间

    try:
        # 查询任务信息（用于记录审计日志）
        try:
            result = await lock_db.execute(
                select(ScheduledTask).where(ScheduledTask.task_name == task_name)
            )
            task_record = result.scalar_one_or_none()
            if task_record:
                task_id = task_record.id
        except Exception as e:
            logger.warning(f"查询任务信息失败（不影响任务执行）: {e}")

        log_scheduled_task_start(
            task_name,
            pid=get_current_pid(),
            host=CURRENT_HOST,
            cron_expression=task_record.cron_expression if task_record else None,
        )

        # 执行任务
        try:
            if asyncio.iscoroutinefunction(task_func):
                await task_func(*args, **kwargs)
            else:
                # 同步函数，在线程池中执行，避免阻塞事件循环
                await asyncio.to_thread(task_func, *args, **kwargs)

            # 计算执行时间（使用北京时间）
            end_time = get_app_now_naive()
            execution_duration = (end_time - start_time).total_seconds()

            # 尝试从任务函数获取执行结果（如果任务保存了结果信息）
            result_message = None
            try:
                result_message = get_task_result(task_name)
            except (ImportError, AttributeError) as e:
                logger.debug(f"从任务结果注册表获取结果失败: {e}")
            except Exception as e:
                logger.debug(f"获取任务执行结果失败: {e}")

            # 释放锁，标记成功
            # 如果任务提供了result_message，会保存到last_error字段
            await release_task_lock(lock_db, task_name, success=True, result_message=result_message)
            success_msg = f"任务 '{task_name}' 执行成功（耗时: {round(execution_duration, 2)}秒）"
            logger.debug(success_msg)

            # 记录审计日志（成功）- 使用新的数据库会话避免事务冲突
            audit_db = None
            try:
                audit_db = AsyncSessionLocal()
                logger.debug(f"开始记录任务 '{task_name}' 的执行审计日志（成功）")
                await log_user_action(
                    db=audit_db,
                    action_type="TASK_RUN",
                    user_id=None,
                    username="SYSTEM",
                    resource_type="SCHEDULED_TASK",
                    resource_id=task_id,
                    resource_name=task_name,
                    ip_address=f"{CURRENT_HOST}:{get_current_pid()}",
                    success=True,
                    details={
                        "task_name": task_name,
                        "pid": get_current_pid(),
                        "host": CURRENT_HOST,
                        "execution_duration_seconds": round(execution_duration, 2),
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "description": task_record.description if task_record else None,
                        "cron_expression": task_record.cron_expression if task_record else None
                    }
                )
                await audit_db.commit()
                logger.debug(f"任务 '{task_name}' 的执行审计日志已成功记录（成功）")
            except Exception as log_error:
                # 日志记录失败不应该影响任务执行，但需要详细记录错误信息
                logger.error(
                    f"记录任务 '{task_name}' 执行审计日志失败（成功）: {log_error}",
                    exc_info=True
                )
            finally:
                if audit_db:
                    try:
                        await audit_db.close()
                    except Exception as close_error:
                        logger.warning(f"关闭审计日志数据库会话失败: {close_error}")

        except Exception as e:
            end_time = get_app_now_naive()
            execution_duration = (end_time - start_time).total_seconds()
            error_msg = log_scheduled_task_failure(
                task_name,
                e,
                duration_seconds=execution_duration,
                pid=get_current_pid(),
                host=CURRENT_HOST,
                cron_expression=task_record.cron_expression if task_record else None,
                exc_info=True,
            )

            # 尝试从任务函数获取执行结果（即使失败也可能有部分结果信息）
            result_message = None
            try:
                result_message = get_task_result(task_name)
            except (ImportError, AttributeError) as e:
                logger.debug(f"从任务结果注册表获取结果失败: {e}")
            except Exception as e:
                logger.debug(f"获取任务执行结果失败: {e}")

            # 如果仍然没有结果，使用错误信息
            if not result_message:
                result_message = error_msg
            # 如果有结果信息且不是错误信息本身，将其与错误信息合并
            elif result_message != error_msg:
                result_message = f"{result_message} | 错误: {error_msg}"

            # 释放锁，标记失败
            # 将执行结果（包括错误信息）保存到last_error字段
            await release_task_lock(
                lock_db,
                task_name,
                success=False,
                result_message=result_message
            )

            # 记录审计日志（失败）- 使用新的数据库会话避免事务冲突
            audit_db = None
            try:
                audit_db = AsyncSessionLocal()
                logger.debug(f"开始记录任务 '{task_name}' 的执行审计日志（失败）")
                await log_user_action(
                    db=audit_db,
                    action_type="TASK_RUN",
                    user_id=None,
                    username="SYSTEM",
                    resource_type="SCHEDULED_TASK",
                    resource_id=task_id,
                    resource_name=task_name,
                    ip_address=f"{CURRENT_HOST}:{get_current_pid()}",
                    success=False,
                    error_message=error_msg,
                    details={
                        "task_name": task_name,
                        "pid": get_current_pid(),
                        "host": CURRENT_HOST,
                        "execution_duration_seconds": round(execution_duration, 2),
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "description": task_record.description if task_record else None,
                        "cron_expression": task_record.cron_expression if task_record else None
                    }
                )
                await audit_db.commit()
                logger.debug(f"任务 '{task_name}' 的执行审计日志已成功记录（失败）")
            except Exception as log_error:
                # 日志记录失败不应该影响任务执行，但需要详细记录错误信息
                logger.error(
                    f"记录任务 '{task_name}' 执行审计日志失败（失败）: {log_error}",
                    exc_info=True
                )
            finally:
                if audit_db:
                    try:
                        await audit_db.close()
                    except Exception as close_error:
                        logger.warning(f"关闭审计日志数据库会话失败: {close_error}")

    finally:
        # 确保数据库会话被正确关闭
        if lock_db:
            try:
                await lock_db.close()
            except Exception as e:
                logger.warning(
                    f"关闭任务 '{task_name}' 的数据库会话时出错: {e}"
                )


def register_scheduled_task(
        task_name: str,
        task_func: Callable[..., Any],
        cron_expression: Optional[str] = None,
        interval_seconds: Optional[int] = None,
        description: Optional[str] = None,
        *args: Any,
        **kwargs: Any
) -> None:
    """
    注册定时任务到调度器
    
    Args:
        task_name: 任务名称（唯一标识）
        task_func: 任务函数（可以是同步或异步函数）
        cron_expression: Cron表达式（例如: "0 0 * * *" 表示每天0点执行）
        interval_seconds: 间隔秒数（与 cron_expression 二选一）
        description: 任务描述
        *args: 任务函数位置参数
        **kwargs: 任务函数关键字参数
        
    Raises:
        ValueError: 如果既没有指定 cron_expression 也没有指定 interval_seconds
    """
    sched = get_scheduler()

    # 创建包装函数，确保带锁执行
    # 定时触发时，不跳过进程检查（skip_process_check=False）
    async def locked_task() -> None:
        """APScheduler 回调：按 cron/interval 触发时走带锁执行（含进程分配）。"""
        await execute_task_with_lock(task_name, task_func, skip_process_check=False, *args, **kwargs)

    # 确定触发器
    if cron_expression:
        trigger = CronTrigger.from_crontab(cron_expression, timezone=DEFAULT_TIMEZONE)
        schedule_info = f"Cron: {cron_expression}"
    elif interval_seconds:
        if interval_seconds <= 0:
            raise ValueError(f"interval_seconds 必须大于 0，当前值: {interval_seconds}")
        trigger = IntervalTrigger(seconds=interval_seconds, timezone=DEFAULT_TIMEZONE)
        schedule_info = f"每 {interval_seconds} 秒"
    else:
        raise ValueError("必须指定 cron_expression 或 interval_seconds 之一")

    # 添加任务到调度器
    sched.add_job(
        locked_task,
        trigger=trigger,
        id=task_name,
        name=task_name,
        replace_existing=True,
        max_instances=1,  # 确保同一任务最多1个实例
        coalesce=True,  # 合并被跳过的执行
        misfire_grace_time=DEFAULT_MISFIRE_GRACE_TIME  # 错过执行时间后60秒内仍可执行
    )

    worker_pid = os.getpid()

    # 计算下次执行时间
    next_run_str = "未计划"
    try:
        jobs = sched.get_jobs()
        for job in jobs:
            if job.id == task_name:
                next_run_str = format_job_next_run_time(job)
                break
    except Exception:
        pass

    logger.info(
        f"[Worker PID:{worker_pid}] 定时任务已注册: '{task_name}' "
        f"({schedule_info}) - {description or '无描述'}, "
        f"下次执行时间: {next_run_str}"
    )


async def init_scheduled_tasks() -> None:
    """
    初始化所有定时任务（在应用启动时调用）
    从数据库的 scheduled_tasks 表中读取任务配置并自动注册
    
    Raises:
        Exception: 如果数据库连接失败，会记录错误但不抛出异常
    """
    logger.info("正在初始化定时任务...")

    # 首先注册所有可用的任务函数
    auto_register_tasks()
    # 自动注册所有任务的结果获取函数
    auto_register_task_results()

    # 从数据库读取任务配置
    db = AsyncSessionLocal()
    registered_count = 0
    skipped_count = 0

    try:
        # 查询所有启用的任务
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.is_active == True)
        )
        tasks = result.scalars().all()

        if not tasks:
            logger.debug("数据库中没有启用的定时任务")
            return

        logger.debug(f"从数据库读取到 {len(tasks)} 个启用的任务")

        for task_record in tasks:
            # 获取任务函数（使用统一的获取逻辑）
            task_func = get_task_function_by_name_or_path(
                task_record.task_name,
                task_record.function_path
            )

            if task_func is None:
                logger.warning(
                    f"任务 '{task_record.task_name}' 在数据库中，"
                    f"但未找到对应的任务函数（function_path: {task_record.function_path}），跳过注册"
                )
                skipped_count += 1
                continue

            # 检查是否有 cron_expression
            if not task_record.cron_expression:
                logger.warning(
                    f"任务 '{task_record.task_name}' 没有设置 cron_expression，跳过注册"
                )
                skipped_count += 1
                continue

            # 注册任务的进程分配
            try:
                await register_task_process_assignment(
                    task_record.task_name,
                    task_record.cron_expression,
                    db
                )
            except Exception as e:
                logger.warning(f"注册任务进程分配失败: {e}")

            # 注册任务
            try:
                register_scheduled_task(
                    task_name=task_record.task_name,
                    task_func=task_func,
                    cron_expression=task_record.cron_expression,
                    description=task_record.description or f"自动注册的任务: {task_record.task_name}"
                )
                registered_count += 1
            except ValueError as e:
                # 参数错误（如无效的 cron 表达式）
                logger.error(
                    f"注册任务 '{task_record.task_name}' 失败（参数错误）: {e}"
                )
                skipped_count += 1
            except Exception as e:
                # 其他异常
                logger.error(
                    f"注册任务 '{task_record.task_name}' 失败: {e}",
                    exc_info=True
                )
                skipped_count += 1

    except Exception as e:
        logger.error(
            f"从数据库读取任务配置失败: {e}",
            exc_info=True
        )
    finally:
        try:
            await db.close()
        except Exception as e:
            logger.warning(f"关闭数据库会话时出错: {e}")

    # 输出初始化结果
    worker_pid = os.getpid()
    logger.info(
        f"[Worker PID:{worker_pid}] 定时任务初始化完成: "
        f"成功注册 {registered_count} 个任务, "
        f"跳过 {skipped_count} 个任务"
    )

    # 如果注册了任务，输出详细信息
    if registered_count > 0:
        logger.info(f"[Worker PID:{worker_pid}] 已注册的任务将在调度器启动后开始执行")
    elif skipped_count > 0:
        logger.warning(
            f"[Worker PID:{worker_pid}] 警告：所有任务都被跳过，可能的原因："
            f"1. 任务函数未找到（检查 function_path 是否正确）"
            f"2. cron_expression 未设置或格式错误"
            f"3. 任务未启用（is_active=False）"
        )
    else:
        logger.warning(
            f"[Worker PID:{worker_pid}] 警告：数据库中没有启用的定时任务！"
            f"请检查 scheduled_tasks 表，确保有任务且 is_active=True"
        )


async def start_scheduler() -> None:
    """
    启动调度器
    
    Raises:
        RuntimeError: 如果调度器启动失败
    """
    sched = get_scheduler()
    if not sched.running:
        try:
            sched.start()
            worker_pid = os.getpid()

            # 获取所有已注册的任务
            jobs = sched.get_jobs()
            job_count = len(jobs)

            logger.info(
                f"[Worker PID:{worker_pid}] 定时任务调度器已启动，"
                f"当前已注册 {job_count} 个任务"
            )

            # 详细输出每个任务的调度信息
            if jobs:
                logger.info(f"[Worker PID:{worker_pid}] 已注册的任务列表:")
                for job in jobs:
                    next_run_str = format_job_next_run_time(job)
                    logger.info(
                        f"  - 任务ID: {job.id}, "
                        f"名称: {job.name}, "
                        f"下次执行时间: {next_run_str}, "
                        f"触发器: {job.trigger}"
                    )
            else:
                logger.warning(
                    f"[Worker PID:{worker_pid}] 警告：调度器已启动，但没有任何任务已注册！"
                    f"请检查数据库中的 scheduled_tasks 表，确保有启用的任务（is_active=True）"
                )
        except Exception as e:
            logger.error(f"启动调度器失败: {e}", exc_info=True)
            raise RuntimeError(f"启动调度器失败: {e}") from e
    else:
        logger.warning("调度器已经在运行中")


async def shutdown_scheduler() -> None:
    """
    关闭调度器
    
    等待所有正在执行的任务完成后再关闭
    """
    mark_scheduler_shutting_down()
    sched = get_scheduler()
    if sched.running:
        try:
            sched.pause()
            sched.shutdown(wait=True)
            logger.info("定时任务调度器已关闭")
        except asyncio.CancelledError:
            # 应用关闭时任务被取消是正常的，不需要记录错误
            logger.debug("调度器关闭时任务被取消（正常关闭流程）")
        except Exception as e:
            logger.error(f"关闭调度器时出错: {e}", exc_info=True)
    else:
        logger.info("调度器未运行，无需关闭")
