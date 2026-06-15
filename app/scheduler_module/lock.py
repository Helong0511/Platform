"""
定时任务分布式锁模块。

功能说明：
- 基于 ``scheduled_task_locks`` 表行锁实现跨进程互斥
- ``acquire_task_lock`` / ``release_task_lock`` 包裹任务执行，超时自动释放

在系统中的位置：
- 被 ``scheduler.execute_task_with_lock`` 调用

注意事项：
1. 锁标识包含 host+pid，防止僵尸锁；异常退出依赖超时回收
2. 任务执行时间超过 DEFAULT_TIMEOUT_SECONDS 可能导致锁被误释放，须合理设置超时
"""
import logging
import os
import socket
from typing import Optional

import pytz
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db_errors import is_database_unreachable_error
from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive, APP_TIMEZONE
from app.models.models import ScheduledTask

logger = logging.getLogger(__name__)

# 常量配置
DEFAULT_TIMEOUT_SECONDS = 300  # 默认超时时间（秒）
MAX_ERROR_MESSAGE_LENGTH = 1000  # 错误信息最大长度

# 主机名在模块加载时计算即可；进程 ID 必须在运行时获取（Gunicorn preload/fork 后不能缓存）
CURRENT_HOST = socket.gethostname()


def get_current_pid() -> int:
    """获取当前进程 ID（勿使用模块级缓存，fork 后会变成 master PID）"""
    return os.getpid()

# 时区配置（从统一配置读取）
UTC_TZ = pytz.UTC
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)  # 应用时区（用于显示和调度器）
# 保持向后兼容的别名
CHINA_TZ = APP_TIMEZONE


async def acquire_task_lock(
        task_name: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
) -> tuple[bool, Optional[AsyncSession]]:
    """
    尝试获取任务锁（确保多进程环境下只有一个进程能执行任务）
    
    使用数据库行锁（SELECT ... FOR UPDATE）确保原子性操作
    关键：所有检查和更新操作都在同一个事务中完成，确保原子性
    
    Args:
        task_name: 任务名称
        timeout_seconds: 如果任务正在运行，等待超时时间（秒）
    
    Returns:
        tuple[bool, Optional[AsyncSession]]: (是否成功获取锁, 数据库会话)
    """
    db = AsyncSessionLocal()
    try:
        # 开始事务，使用 SELECT ... FOR UPDATE 获取行锁
        # 这样可以确保在事务提交前，其他进程无法修改这条记录
        # MySQL 兼容：不使用 nowait，通过应用层检查 is_running 状态
        result = await db.execute(
            select(ScheduledTask)
            .where(
                and_(
                    ScheduledTask.task_name == task_name,
                    ScheduledTask.is_active == True
                )
            )
            .with_for_update(of=ScheduledTask)
        )
        task_record = result.scalar_one_or_none()

        if task_record is None:
            # 任务记录不存在，创建新记录
            task_record = ScheduledTask(
                task_name=task_name,
                is_running=False,
                run_count=0,
                success_count=0,
                error_count=0,
                is_active=True
            )
            db.add(task_record)
            await db.flush()
            # 重新获取行锁（对新创建的记录）
            result = await db.execute(
                select(ScheduledTask)
                .where(ScheduledTask.task_name == task_name)
                .with_for_update(of=ScheduledTask)
            )
            task_record = result.scalar_one()

        # 原子性检查：在持有行锁的情况下检查任务状态
        # 这样可以确保没有其他进程能同时修改这个记录
        if task_record.is_running:
            # 检查是否超时（可能是上次执行异常导致锁未释放）
            if task_record.last_run_time:
                # 确保 last_run_time 是 naive datetime（数据库存储的是北京时间）
                if task_record.last_run_time.tzinfo is None:
                    # 如果数据库返回的是 naive datetime，假设是北京时间
                    last_run_app = task_record.last_run_time
                else:
                    # 如果带时区信息，转换为北京时间（naive）
                    last_run_app = task_record.last_run_time.astimezone(APP_TIMEZONE).replace(tzinfo=None)
                time_diff = (get_app_now_naive() - last_run_app).total_seconds()
                if time_diff > timeout_seconds:
                    # 超时，释放锁（在同一个事务中）
                    logger.warning(
                        f"任务 {task_name} 执行超时（{time_diff:.1f}秒），释放锁。"
                        f"上次执行进程: PID {task_record.last_run_pid}@{task_record.last_run_host}"
                    )
                    task_record.is_running = False
                    task_record.last_error = "任务执行超时，自动释放锁"
                else:
                    # 任务正在运行，无法获取锁
                    logger.debug(
                        f"任务 {task_name} 正在运行中（进程ID: {task_record.last_run_pid}, "
                        f"主机: {task_record.last_run_host}，运行时间: {time_diff:.1f}秒），跳过本次执行"
                    )
                    await db.rollback()
                    await db.close()
                    return False, None
            else:
                # is_running=True 但没有 last_run_time，异常状态，释放锁
                logger.warning(f"任务 {task_name} 状态异常（is_running=True 但无 last_run_time），释放锁")
                task_record.is_running = False

        # 原子性更新：在持有行锁的情况下更新任务状态
        # 确保只有当前进程能成功更新，其他进程会因为行锁而等待或失败
        task_record.is_running = True
        task_record.last_run_pid = get_current_pid()
        task_record.last_run_host = CURRENT_HOST
        # 存储北京时间到数据库（数据库统一使用北京时间）
        task_record.last_run_time = get_app_now_naive()
        task_record.run_count += 1
        task_record.last_error = None  # 清除上次错误

        # 提交事务，释放行锁
        await db.commit()
        logger.debug(
            f"任务 {task_name} 成功获取锁（进程ID: {get_current_pid()}, 主机: {CURRENT_HOST}）"
        )
        return True, db

    except Exception as e:
        # 维护/停库期间不记 ERROR，避免部署窗口误报
        if is_database_unreachable_error(e):
            logger.warning(f"数据库不可用，无法获取任务锁: {task_name}")
            await db.rollback()
            await db.close()
            return False, None

        # 处理各种可能的异常
        error_str = str(e)
        # MySQL 锁相关错误
        if "Lock wait timeout" in error_str or "Deadlock" in error_str or "Lock" in error_str:
            logger.info(
                f"任务 {task_name} 无法获取锁（其他进程正在执行），跳过本次执行"
            )
            await db.rollback()
            await db.close()
            return False, None
        # MySQL 语法错误（如 NOWAIT 不支持）
        elif "NOWAIT" in error_str or "syntax" in error_str.lower():
            logger.warning(
                f"MySQL 语法错误（可能是版本不支持 NOWAIT），尝试使用普通 FOR UPDATE: {error_str}"
            )
            # 重试：使用普通 FOR UPDATE（不带 NOWAIT）
            try:
                result = await db.execute(
                    select(ScheduledTask)
                    .where(
                        and_(
                            ScheduledTask.task_name == task_name,
                            ScheduledTask.is_active == True
                        )
                    )
                    .with_for_update(of=ScheduledTask)
                )
                task_record = result.scalar_one_or_none()

                if task_record is None:
                    # 任务记录不存在，创建新记录
                    task_record = ScheduledTask(
                        task_name=task_name,
                        is_running=False,
                        run_count=0,
                        success_count=0,
                        error_count=0,
                        is_active=True
                    )
                    db.add(task_record)
                    await db.flush()
                    # 重新获取行锁
                    result = await db.execute(
                        select(ScheduledTask)
                        .where(ScheduledTask.task_name == task_name)
                        .with_for_update(of=ScheduledTask)
                    )
                    task_record = result.scalar_one()

                if task_record.is_running:
                    # 检查是否超时
                    if task_record.last_run_time:
                        # 确保 last_run_time 是 naive datetime（数据库存储的是北京时间）
                        if task_record.last_run_time.tzinfo is None:
                            # 如果数据库返回的是 naive datetime，假设是北京时间
                            last_run_app = task_record.last_run_time
                        else:
                            # 如果带时区信息，转换为北京时间（naive）
                            last_run_app = task_record.last_run_time.astimezone(APP_TIMEZONE).replace(tzinfo=None)
                        time_diff = (get_app_now_naive() - last_run_app).total_seconds()
                        if time_diff > timeout_seconds:
                            logger.warning(
                                f"任务 {task_name} 执行超时（{time_diff:.1f}秒），释放锁。"
                                f"上次执行进程: PID {task_record.last_run_pid}@{task_record.last_run_host}"
                            )
                            task_record.is_running = False
                            task_record.last_error = "任务执行超时，自动释放锁"
                        else:
                            logger.debug(f"任务 {task_name} 正在运行中，跳过本次执行")
                            await db.rollback()
                            await db.close()
                            return False, None
                    else:
                        logger.warning(f"任务 {task_name} 状态异常（is_running=True 但无 last_run_time），释放锁")
                        task_record.is_running = False

                # 更新任务状态
                task_record.is_running = True
                task_record.last_run_pid = get_current_pid()
                task_record.last_run_host = CURRENT_HOST
                task_record.last_run_time = get_app_now_naive()  # 使用北京时间
                task_record.run_count += 1
                task_record.last_error = None

                await db.commit()
                logger.debug(
                    f"任务 {task_name} 成功获取锁（进程ID: {get_current_pid()}, 主机: {CURRENT_HOST}）"
                )
                return True, db
            except Exception as retry_e:
                logger.error(f"重试获取锁失败: {task_name}, 错误: {retry_e}", exc_info=True)
                await db.rollback()
                await db.close()
                return False, None
        else:
            logger.error(f"获取任务锁失败: {task_name}, 错误: {e}", exc_info=True)
            await db.rollback()
            await db.close()
            return False, None


async def release_task_lock(
        db: AsyncSession,
        task_name: str,
        success: bool = True,
        error_message: Optional[str] = None,
        result_message: Optional[str] = None
) -> None:
    """
    释放任务锁并更新执行结果
    
    使用行锁确保原子性更新，防止多进程环境下的竞态条件
    
    Args:
        db: 数据库会话（应该是在 acquire_task_lock 中获取的同一个会话）
        task_name: 任务名称
        success: 是否执行成功
        error_message: 错误信息（如果失败，已废弃，使用result_message）
        result_message: 执行结果信息（成功或失败的详细信息，会保存到last_error字段）
    """
    try:
        # 使用行锁确保原子性更新
        # 注意：这里使用同一个 db 会话，已经在 acquire_task_lock 中获取了锁
        # 所以不需要再次获取锁，直接查询即可
        result = await db.execute(
            select(ScheduledTask)
            .where(ScheduledTask.task_name == task_name)
        )
        task_record = result.scalar_one_or_none()

        if task_record:
            # 严格验证锁的所有权（确保是当前进程持有的锁）
            # 如果锁不属于当前进程，记录警告但不释放锁（防止误释放其他进程的锁）
            current_pid = get_current_pid()
            if task_record.last_run_pid != current_pid or task_record.last_run_host != CURRENT_HOST:
                logger.warning(
                    f"任务 {task_name} 锁的所有权不匹配，拒绝释放锁。"
                    f"当前进程: {current_pid}@{CURRENT_HOST}, "
                    f"锁持有者: {task_record.last_run_pid}@{task_record.last_run_host}"
                )
                await db.rollback()
                return  # 不释放其他进程的锁

            # 原子性更新：在持有行锁的情况下更新状态
            task_record.is_running = False
            # 存储北京时间到数据库（数据库统一使用北京时间）
            task_record.updated_at = get_app_now_naive()

            if success:
                task_record.success_count += 1
            else:
                task_record.error_count += 1

            # 保存执行结果信息到last_error字段（无论成功还是失败）
            # 优先使用result_message，如果没有则使用error_message（向后兼容）
            result_info = result_message or error_message
            if result_info:
                # 限制信息长度，避免数据库字段溢出
                task_record.last_error = result_info[:MAX_ERROR_MESSAGE_LENGTH]
            else:
                # 如果没有提供结果信息，成功时清除，失败时保留（向后兼容）
                if success:
                    task_record.last_error = None
                # 失败时如果没有提供信息，last_error保持原值（可能是之前的错误）

            await db.commit()
            if success:
                logger.debug(
                    f"任务 {task_name} 锁已释放，执行成功 "
                    f"（进程ID: {get_current_pid()}, 主机: {CURRENT_HOST}）"
                )
            else:
                from app.scheduler_module.task_utils import log_scheduled_task_failure_recorded

                log_scheduled_task_failure_recorded(
                    task_name,
                    result_info,
                    error_count=task_record.error_count,
                    success_count=task_record.success_count,
                    run_count=task_record.run_count,
                )
        else:
            logger.warning(f"任务记录不存在: {task_name}")
            await db.rollback()

    except Exception as e:
        await db.rollback()
        logger.error(f"释放任务锁失败: {task_name}, 错误: {e}", exc_info=True)
        # 即使释放锁失败，也不抛出异常，避免影响任务执行结果
