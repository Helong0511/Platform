"""
定时任务分布式锁模块。

功能说明：
- 基于 ``scheduled_tasks`` 表行锁实现跨进程互斥
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db_errors import is_database_unreachable_error, is_duplicate_entry_error
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


def _last_run_app_naive(last_run_time) -> Optional[object]:
    """将 last_run_time 转为应用时区的 naive datetime。"""
    if last_run_time is None:
        return None
    if last_run_time.tzinfo is None:
        return last_run_time
    return last_run_time.astimezone(APP_TIMEZONE).replace(tzinfo=None)


async def _select_task_for_update(
    db: AsyncSession,
    task_name: str,
) -> Optional[ScheduledTask]:
    """按 task_name 加行锁查询（不按 is_active 过滤，避免误判记录不存在）。"""
    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.task_name == task_name)
        .with_for_update(of=ScheduledTask)
    )
    return result.scalar_one_or_none()


async def _load_or_create_task_record(
    db: AsyncSession,
    task_name: str,
) -> Optional[ScheduledTask]:
    """
    加载任务记录；不存在时尝试创建。

    并发插入冲突时回滚并重新 SELECT，避免 Duplicate entry 导致任务被跳过。
    """
    task_record = await _select_task_for_update(db, task_name)
    if task_record is not None:
        return task_record

    db.add(
        ScheduledTask(
            task_name=task_name,
            is_running=False,
            run_count=0,
            success_count=0,
            error_count=0,
            is_active=True,
        )
    )
    try:
        await db.flush()
    except Exception as exc:
        if not is_duplicate_entry_error(exc):
            raise
        logger.debug("任务 '%s' 并发创建记录冲突，改为加载已有行", task_name)
        await db.rollback()
        return await _select_task_for_update(db, task_name)

    return await _select_task_for_update(db, task_name)


def _resolve_stale_running_lock(
    task_record: ScheduledTask,
    task_name: str,
    timeout_seconds: int,
) -> bool:
    """
    处理 is_running 状态。

    返回 True 表示可继续抢占锁；False 表示其他进程仍在执行且未超时。
    """
    if not task_record.is_running:
        return True

    last_run_app = _last_run_app_naive(task_record.last_run_time)
    if last_run_app is not None:
        time_diff = (get_app_now_naive() - last_run_app).total_seconds()
        if time_diff > timeout_seconds:
            logger.warning(
                "任务 %s 执行超时（%.1f秒），释放锁。上次执行进程: PID %s@%s",
                task_name,
                time_diff,
                task_record.last_run_pid,
                task_record.last_run_host,
            )
            task_record.is_running = False
            task_record.last_error = "任务执行超时，自动释放锁"
            return True

        logger.debug(
            "任务 %s 正在运行中（进程ID: %s, 主机: %s，运行时间: %.1f秒），跳过本次执行",
            task_name,
            task_record.last_run_pid,
            task_record.last_run_host,
            time_diff,
        )
        return False

    logger.warning("任务 %s 状态异常（is_running=True 但无 last_run_time），释放锁", task_name)
    task_record.is_running = False
    return True


def _claim_task_lock(task_record: ScheduledTask) -> None:
    """将任务标记为当前进程持有锁。"""
    task_record.is_running = True
    task_record.last_run_pid = get_current_pid()
    task_record.last_run_host = CURRENT_HOST
    task_record.last_run_time = get_app_now_naive()
    task_record.run_count += 1
    task_record.last_error = None


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
        task_record = await _load_or_create_task_record(db, task_name)
        if task_record is None:
            logger.warning("任务记录不存在且无法加载: %s", task_name)
            await db.rollback()
            await db.close()
            return False, None

        if not task_record.is_active:
            logger.debug("任务 %s 已禁用（is_active=False），跳过获取锁", task_name)
            await db.rollback()
            await db.close()
            return False, None

        if not _resolve_stale_running_lock(task_record, task_name, timeout_seconds):
            await db.rollback()
            await db.close()
            return False, None

        _claim_task_lock(task_record)
        await db.commit()
        logger.debug(
            "任务 %s 成功获取锁（进程ID: %s, 主机: %s）",
            task_name,
            get_current_pid(),
            CURRENT_HOST,
        )
        return True, db

    except Exception as e:
        if is_database_unreachable_error(e):
            logger.warning("数据库不可用，无法获取任务锁: %s", task_name)
            await db.rollback()
            await db.close()
            return False, None

        error_str = str(e)
        if (
            "Lock wait timeout" in error_str
            or "Deadlock" in error_str
            or ("Lock" in error_str and "Duplicate entry" not in error_str)
        ):
            logger.info("任务 %s 无法获取锁（其他进程正在执行），跳过本次执行", task_name)
            await db.rollback()
            await db.close()
            return False, None

        if is_duplicate_entry_error(e):
            logger.info(
                "任务 %s 获取锁时发生唯一键冲突，跳过本次执行（其他进程可能已抢占）",
                task_name,
            )
            await db.rollback()
            await db.close()
            return False, None

        logger.error("获取任务锁失败: %s, 错误: %s", task_name, e, exc_info=True)
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
