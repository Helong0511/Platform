"""
进程任务分配器
根据任务的执行时间（cron表达式）将任务分配到不同的进程执行
实现跨进程的任务负载均衡
"""
import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.models import ScheduledTask
from app.scheduler_module.lock import get_current_pid, CURRENT_HOST
from app.scheduler_module.task_queue import get_task_queue

logger = logging.getLogger(__name__)


def _is_dedicated_scheduler_process() -> bool:
    """独立调度服务（Platform-scheduler）仅 1 worker，不做跨进程分配。"""
    return os.getenv("GUNICORN_ROLE", "api").strip().lower() == "scheduler"


# 尝试导入psutil，如果不可用则使用备用方法
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil未安装，将使用备用方法检查进程存在性。建议安装: pip install psutil>=5.9.0")

# 进程任务分配缓存（进程ID -> 任务名称列表）
_process_task_assignments: Dict[int, List[str]] = {}

# 任务执行时间分组（cron表达式 -> 进程ID列表）
_cron_process_groups: Dict[str, List[int]] = {}


def get_cron_hash(cron_expression: str) -> str:
    """
    获取cron表达式的哈希值（用于分组）
    
    Args:
        cron_expression: Cron表达式
        
    Returns:
        Cron表达式的哈希值
    """
    return hashlib.md5(cron_expression.encode('utf-8')).hexdigest()[:8]


def is_process_alive(pid: int) -> bool:
    """
    检查进程是否还存在
    
    Args:
        pid: 进程ID
        
    Returns:
        bool: True表示进程存在，False表示进程不存在
    """
    if not pid or pid <= 0:
        return False

    if PSUTIL_AVAILABLE:
        try:
            return psutil.pid_exists(pid)
        except Exception as e:
            logger.debug(f"检查进程 {pid} 存在性时出错: {e}")
            # 如果检查失败，假设进程存在（保守策略）
            return True
    else:
        # 备用方法：尝试向进程发送信号0（不实际发送信号，只检查进程是否存在）
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            # 进程不存在或没有权限
            return False
        except Exception as e:
            logger.debug(f"检查进程 {pid} 存在性时出错: {e}")
            # 如果检查失败，假设进程存在（保守策略）
            return True


def filter_alive_processes(processes: List[int]) -> List[int]:
    """
    过滤掉不存在的进程
    
    Args:
        processes: 进程ID列表
        
    Returns:
        过滤后的进程ID列表（只包含存在的进程）
    """
    alive_processes = [pid for pid in processes if is_process_alive(pid)]

    if len(alive_processes) < len(processes):
        dead_processes = set(processes) - set(alive_processes)
        logger.debug(
            f"过滤掉不存在的进程: {sorted(dead_processes)} "
            f"（剩余活跃进程: {sorted(alive_processes)}）"
        )

    return alive_processes


async def get_process_for_task(
        task_name: str,
        cron_expression: str,
        db: Optional[AsyncSession] = None
) -> Tuple[bool, Optional[int]]:
    """
    为任务分配进程ID
    
    策略：
    1. 根据cron表达式分组，相同执行时间的任务分配到不同进程
    2. 如果当前进程未达到上限，使用当前进程
    3. 如果当前进程达到上限，查找其他空闲进程
    
    Args:
        task_name: 任务名称
        cron_expression: Cron表达式
        db: 数据库会话（可选）
        
    Returns:
        tuple[bool, Optional[int]]: (是否应该执行, 分配的进程ID)
        - 如果返回 (True, pid)，表示应该由指定进程执行
        - 如果返回 (False, None)，表示应该跳过（由其他进程执行）
    """

    max_concurrent = getattr(settings, 'MAX_CONCURRENT_SCHEDULED_TASKS', 2)
    current_pid = get_current_pid()

    # 独立调度进程：全部在本 worker 执行，避免误分到已关闭调度器的 API worker
    if _is_dedicated_scheduler_process():
        return True, current_pid

    # 从数据库查询相同cron表达式的任务，确定应该由哪个进程执行
    if db is None:
        db = AsyncSessionLocal()
        should_close = True
    else:
        should_close = False

    try:
        # 查询所有相同cron表达式的任务
        result = await db.execute(
            select(ScheduledTask)
            .where(
                and_(
                    ScheduledTask.cron_expression == cron_expression,
                    ScheduledTask.is_active == True
                )
            )
            .order_by(ScheduledTask.id)
        )
        tasks_with_same_cron = result.scalars().all()

        if not tasks_with_same_cron:
            # 没有找到相同cron的任务，使用当前进程
            # 检查当前进程是否达到上限
            queue = get_task_queue()
            queue_status = await queue.get_queue_status()
            current_running = queue_status['current_running']
            if current_running < max_concurrent:
                return True, current_pid
            return True, current_pid  # 即使满载也使用当前进程（排队）

        # 找到当前任务在相同cron任务列表中的索引
        task_index = -1
        for idx, task in enumerate(tasks_with_same_cron):
            if task.task_name == task_name:
                task_index = idx
                break

        if task_index == -1:
            # 未找到任务，使用当前进程
            queue = get_task_queue()
            queue_status = await queue.get_queue_status()
            current_running = queue_status['current_running']
            if current_running < max_concurrent:
                return True, current_pid
            return True, current_pid

        # 查询所有活跃进程及其当前运行的任务数
        result = await db.execute(
            select(
                ScheduledTask.last_run_pid,
                func.count(ScheduledTask.id).label('running_count')
            )
            .where(
                and_(
                    ScheduledTask.is_active == True,
                    ScheduledTask.is_running == True,
                    ScheduledTask.last_run_pid.isnot(None)
                )
            )
            .group_by(ScheduledTask.last_run_pid)
        )
        process_running_counts = {pid: count for pid, count in result.all() if pid}

        # 获取所有可能的进程ID
        # 策略：不仅查询正在运行任务的进程，还查询最近运行过任务的进程
        # 这样可以发现所有可用的worker进程，即使它们当前没有运行任务

        # 1. 查询正在运行任务的进程
        result = await db.execute(
            select(ScheduledTask.last_run_pid)
            .where(
                and_(
                    ScheduledTask.is_active == True,
                    ScheduledTask.is_running == True,
                    ScheduledTask.last_run_pid.isnot(None)
                )
            )
            .distinct()
        )
        running_processes = sorted([pid for pid, in result.all() if pid])

        # 2. 查询最近运行过任务的进程（即使当前没有运行任务）
        # 优化：缩短时间窗口到2分钟，避免使用过期的进程ID
        # 这样可以发现所有可用的worker进程，但不会使用太旧的进程记录
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=2)  # 最近2分钟内运行过任务的进程
        result = await db.execute(
            select(ScheduledTask.last_run_pid)
            .where(
                and_(
                    ScheduledTask.is_active == True,
                    ScheduledTask.last_run_pid.isnot(None),
                    ScheduledTask.last_run_time >= recent_time
                )
            )
            .distinct()
        )
        recent_processes = sorted([pid for pid, in result.all() if pid])

        # 合并所有进程（去重）
        all_processes_set = set(running_processes + recent_processes)

        # 如果当前进程不在列表中，添加它（因为当前进程可能还没有运行过任务）
        if current_pid not in all_processes_set:
            all_processes_set.add(current_pid)

        all_processes = sorted(list(all_processes_set))

        # 过滤掉不存在的进程（重要：避免使用已退出的进程）
        all_processes = filter_alive_processes(all_processes)

        # 如果当前进程被过滤掉了（不应该发生），重新添加
        if current_pid not in all_processes:
            logger.warning(
                f"当前进程 {current_pid} 不在活跃进程列表中，重新添加。"
                f"这可能表示进程ID获取有问题。"
            )
            all_processes.append(current_pid)
            all_processes = sorted(all_processes)

        # 如果仍然没有任何进程，使用当前进程
        if not all_processes:
            logger.warning(
                f"没有找到任何活跃进程，使用当前进程 {current_pid}。"
                f"这可能表示这是首次运行或所有进程都已退出。"
            )
            all_processes = [current_pid]

        logger.debug(
            f"任务 '{task_name}' 进程分配检查: "
            f"当前进程={current_pid}@{CURRENT_HOST}, "
            f"活跃进程={all_processes} (已过滤不存在的进程), "
            f"任务索引={task_index}, 相同cron任务数={len(tasks_with_same_cron)}"
        )

        # 如果没有其他进程，使用当前进程
        # 单进程环境下，所有相同cron的任务都应该在当前进程执行（可以并发）
        if not all_processes or (len(all_processes) == 1 and all_processes[0] == current_pid):
            queue = get_task_queue()
            queue_status = await queue.get_queue_status()
            current_running = queue_status['current_running']
            logger.debug(
                f"任务 '{task_name}' 单进程环境或首次运行，"
                f"分配给当前进程 {current_pid} "
                f"（当前运行: {current_running}/{max_concurrent}，"
                f"相同cron的任务可以并发执行）"
            )
            # 单进程环境下，即使当前运行数达到上限，也允许任务排队等待
            # 这样可以确保所有任务都能执行，只是需要等待
            return True, current_pid

        # 优先查找空闲的进程（未达到并发上限的进程）
        # 策略：1. 先查找所有空闲进程 2. 如果都满载，再按轮询分配
        assigned_pid = None

        # 获取所有进程的当前运行任务数
        process_loads = {}
        for pid in all_processes:
            if pid == current_pid:
                # 当前进程：从队列状态获取
                queue = get_task_queue()
                queue_status = await queue.get_queue_status()
                process_loads[pid] = queue_status['current_running']
            else:
                # 其他进程：从数据库状态获取
                process_loads[pid] = process_running_counts.get(pid, 0)

        # 查找空闲进程（未达到并发上限的进程）
        idle_processes = [pid for pid in all_processes if process_loads.get(pid, 0) < max_concurrent]

        if idle_processes:
            # 有空闲进程，优先选择负载最低的进程
            # 再次验证进程存在性（双重检查，确保分配的进程真的存在）
            idle_processes = filter_alive_processes(idle_processes)

            if not idle_processes:
                # 所有空闲进程都不存在了，使用当前进程
                logger.warning(
                    f"任务 '{task_name}' 所有空闲进程都不存在，"
                    f"使用当前进程 {current_pid} 执行"
                )
                assigned_pid = current_pid
            else:
                idle_processes.sort(key=lambda pid: process_loads.get(pid, 0))
                assigned_pid = idle_processes[0]
                logger.info(
                    f"任务 '{task_name}' 分配给空闲进程 {assigned_pid}@{CURRENT_HOST} "
                    f"（负载: {process_loads.get(assigned_pid, 0)}/{max_concurrent}，"
                    f"空闲进程: {idle_processes}）"
                )
        else:
            # 所有进程都满载，按任务索引轮询分配（确保相同cron的任务分配到不同进程）
            if len(all_processes) == 1:
                assigned_pid = all_processes[0]
                logger.info(
                    f"任务 '{task_name}' 单进程环境，"
                    f"所有相同cron的任务都在进程 {assigned_pid} 执行（可以并发）"
                )
            else:
                # 多个进程，按索引轮询分配
                # 再次验证进程存在性
                all_processes = filter_alive_processes(all_processes)

                if not all_processes:
                    # 所有进程都不存在了，使用当前进程
                    logger.warning(
                        f"任务 '{task_name}' 所有进程都不存在，"
                        f"使用当前进程 {current_pid} 执行"
                    )
                    assigned_pid = current_pid
                else:
                    assigned_process_index = task_index % len(all_processes)
                    assigned_pid = all_processes[assigned_process_index]
                    logger.info(
                        f"任务 '{task_name}' 所有进程都满载，按轮询分配到进程 {assigned_pid}@{CURRENT_HOST} "
                        f"（任务索引: {task_index}, 进程负载: {process_loads}）"
                    )

        # 如果分配的是当前进程
        if assigned_pid == current_pid:
            # 检查当前进程是否真的可以执行（可能在上面的分配逻辑中已经检查过，但这里再次确认）
            queue = get_task_queue()
            queue_status = await queue.get_queue_status()
            current_running = queue_status['current_running']

            # 如果当前进程未满载，直接执行
            if current_running < max_concurrent:
                logger.debug(
                    f"任务 '{task_name}' 分配给当前进程 {current_pid} "
                    f"（当前运行: {current_running}/{max_concurrent}）"
                )
                return True, current_pid
            else:
                # 当前进程已满载，但上面已经分配给了当前进程（可能是所有进程都满载）
                # 允许在当前进程排队等待
                logger.info(
                    f"任务 '{task_name}' 当前进程 {current_pid} 已满载 "
                    f"（运行: {current_running}/{max_concurrent}），"
                    f"将在当前进程排队等待"
                )
                return True, current_pid
        else:
            # 分配给了其他进程，验证该进程是否真的存在
            if not is_process_alive(assigned_pid):
                # 分配的进程不存在，使用当前进程执行
                logger.warning(
                    f"任务 '{task_name}' 分配的进程 {assigned_pid} 不存在，"
                    f"改用当前进程 {current_pid} 执行"
                )
                return True, current_pid

            # 分配给了其他进程，当前进程应该跳过
            logger.debug(
                f"任务 '{task_name}' 已分配给进程 {assigned_pid}@{CURRENT_HOST} "
                f"（轮询分配），当前进程 {current_pid}@{CURRENT_HOST} 跳过执行"
            )
            return False, assigned_pid

    except Exception as e:
        logger.error(f"获取任务进程分配失败: {e}", exc_info=True)
        # 出错时，检查当前进程是否达到上限
        queue = get_task_queue()
        queue_status = await queue.get_queue_status()
        current_running = queue_status['current_running']
        if current_running < max_concurrent:
            return True, current_pid
        # 否则跳过（让其他进程执行）
        return False, None
    finally:
        if should_close and db:
            await db.close()


async def should_execute_in_current_process(
        task_name: str,
        cron_expression: str,
        db: Optional[AsyncSession] = None
) -> bool:
    """
    判断任务是否应该在当前进程执行
    
    Args:
        task_name: 任务名称
        cron_expression: Cron表达式
        db: 数据库会话（可选）
        
    Returns:
        bool: True表示应该在当前进程执行，False表示应该跳过
    """
    should_execute, assigned_pid = await get_process_for_task(
        task_name, cron_expression, db
    )

    if not should_execute:
        return False

    # 如果分配的是当前进程，检查是否真的应该执行
    if assigned_pid == get_current_pid():
        return True

    # 分配给了其他进程，当前进程应该跳过
    logger.debug(
        f"任务 '{task_name}' 已分配给进程 {assigned_pid}，"
        f"当前进程 {get_current_pid()} 跳过执行"
    )
    return False


async def register_task_process_assignment(
        task_name: str,
        cron_expression: str,
        db: Optional[AsyncSession] = None
) -> None:
    """
    注册任务的进程分配（在任务注册时调用）
    
    Args:
        task_name: 任务名称
        cron_expression: Cron表达式
        db: 数据库会话（可选）
    """
    cron_hash = get_cron_hash(cron_expression)
    pid = get_current_pid()

    # 将任务添加到当前进程的任务列表
    if pid not in _process_task_assignments:
        _process_task_assignments[pid] = []

    if task_name not in _process_task_assignments[pid]:
        _process_task_assignments[pid].append(task_name)

    # 将当前进程添加到该cron表达式的进程组
    if cron_hash not in _cron_process_groups:
        _cron_process_groups[cron_hash] = []

    if pid not in _cron_process_groups[cron_hash]:
        _cron_process_groups[cron_hash].append(pid)

    logger.debug(
        f"任务 '{task_name}' (Cron: {cron_expression}) "
        f"已注册到进程 {pid}"
    )


def get_process_assignments() -> Dict[int, List[str]]:
    """
    获取进程任务分配情况
    
    Returns:
        进程ID到任务名称列表的映射
    """
    return _process_task_assignments.copy()


def get_cron_process_groups() -> Dict[str, List[int]]:
    """
    获取cron表达式到进程ID列表的映射
    
    Returns:
        Cron表达式哈希到进程ID列表的映射
    """
    return _cron_process_groups.copy()


async def cleanup_stale_process_records(
        db: Optional[AsyncSession] = None,
        max_age_minutes: int = 5
) -> int:
    """
    清理数据库中过期的进程记录（超过指定时间未运行的进程）
    
    这个函数可以定期调用，清理不再存在的进程记录，避免进程分配逻辑使用过期的进程ID
    
    Args:
        db: 数据库会话（可选）
        max_age_minutes: 进程记录的最大保留时间（分钟），超过此时间的进程记录将被清理
        
    Returns:
        int: 清理的记录数
    """
    if db is None:
        db = AsyncSessionLocal()
        should_close = True
    else:
        should_close = False

    try:
        # 计算过期时间
        expire_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

        # 查询所有活跃任务，获取它们的last_run_pid
        result = await db.execute(
            select(ScheduledTask.last_run_pid)
            .where(
                and_(
                    ScheduledTask.is_active == True,
                    ScheduledTask.last_run_pid.isnot(None),
                    ScheduledTask.last_run_time < expire_time
                )
            )
            .distinct()
        )
        stale_pids = [pid for pid, in result.all() if pid]

        if not stale_pids:
            return 0

        # 检查这些进程是否真的不存在
        dead_pids = [pid for pid in stale_pids if not is_process_alive(pid)]

        if not dead_pids:
            return 0

        # 清理这些进程的记录（将last_run_pid设为NULL，但保留其他信息）
        # 注意：这里不删除任务记录，只是清理进程ID，让系统重新分配
        cleaned_count = 0
        for pid in dead_pids:
            result = await db.execute(
                select(ScheduledTask)
                .where(
                    and_(
                        ScheduledTask.last_run_pid == pid,
                        ScheduledTask.last_run_time < expire_time,
                        ScheduledTask.is_running == False  # 只清理未运行的任务
                    )
                )
            )
            tasks = result.scalars().all()
            for task in tasks:
                task.last_run_pid = None
                cleaned_count += 1

        if cleaned_count > 0:
            await db.commit()
            logger.info(
                f"清理了 {cleaned_count} 条过期进程记录 "
                f"（进程ID: {sorted(dead_pids)}，超过 {max_age_minutes} 分钟未运行）"
            )

        return cleaned_count

    except Exception as e:
        logger.error(f"清理过期进程记录失败: {e}", exc_info=True)
        if should_close and db:
            await db.rollback()
        return 0
    finally:
        if should_close and db:
            await db.close()
