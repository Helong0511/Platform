"""
进程任务分配器
根据任务的执行时间（cron表达式）将任务分配到不同的进程执行
实现跨进程的任务负载均衡
"""
import os
import logging
import hashlib
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func

from app.core.database import AsyncSessionLocal
from app.models.models import ScheduledTask
from app.scheduler_module.lock import CURRENT_PID, CURRENT_HOST

logger = logging.getLogger(__name__)

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
    from app.scheduler_module.task_queue import get_task_queue
    from app.core.config import settings
    
    max_concurrent = getattr(settings, 'MAX_CONCURRENT_SCHEDULED_TASKS', 2)
    current_pid = CURRENT_PID
    
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
        
        # 获取所有可能的进程ID（从所有任务的last_run_pid）
        # 但是，我们只关心当前正在运行的进程，而不是历史记录
        # 所以应该从 is_running=True 的任务中获取 PID
        result = await db.execute(
            select(ScheduledTask.last_run_pid)
            .where(
                and_(
                    ScheduledTask.is_active == True,
                    ScheduledTask.is_running == True,  # 只考虑正在运行的任务
                    ScheduledTask.last_run_pid.isnot(None)
                )
            )
            .distinct()
        )
        running_processes = sorted([pid for pid, in result.all() if pid])
        
        # 如果当前进程不在运行进程列表中，添加它（因为当前进程可能还没有运行过任务）
        if current_pid not in running_processes:
            running_processes.append(current_pid)
            running_processes.sort()
        
        # 如果没有任何运行中的任务，只有当前进程
        if not running_processes:
            all_processes = [current_pid]
        else:
            all_processes = running_processes
        
        logger.info(
            f"任务 '{task_name}' 进程分配检查: "
            f"当前进程={current_pid}, 运行中的进程={all_processes}, "
            f"任务索引={task_index}, 相同cron任务数={len(tasks_with_same_cron)}"
        )
        
        # 如果没有其他进程，使用当前进程
        # 单进程环境下，所有相同cron的任务都应该在当前进程执行（可以并发）
        if not all_processes or (len(all_processes) == 1 and all_processes[0] == current_pid):
            queue = get_task_queue()
            queue_status = await queue.get_queue_status()
            current_running = queue_status['current_running']
            logger.info(
                f"任务 '{task_name}' 单进程环境或首次运行，"
                f"分配给当前进程 {current_pid} "
                f"（当前运行: {current_running}/{max_concurrent}，"
                f"相同cron的任务可以并发执行）"
            )
            # 单进程环境下，即使当前运行数达到上限，也允许任务排队等待
            # 这样可以确保所有任务都能执行，只是需要等待
            return True, current_pid
        
        # 根据任务索引和进程数量，轮询分配进程
        # 相同cron的任务按顺序分配到不同进程
        # 但是，如果只有一个进程，所有任务都应该在这个进程执行（可以并发）
        if len(all_processes) == 1:
            # 只有一个进程，所有任务都在这个进程执行（可以并发）
            assigned_pid = all_processes[0]
            logger.info(
                f"任务 '{task_name}' 单进程环境，"
                f"所有相同cron的任务都在进程 {assigned_pid} 执行（可以并发）"
            )
        else:
            # 多个进程，按索引轮询分配
            assigned_process_index = task_index % len(all_processes)
            assigned_pid = all_processes[assigned_process_index]
        
        # 如果分配的是当前进程
        if assigned_pid == current_pid:
            # 检查当前进程是否达到上限
            queue = get_task_queue()
            queue_status = await queue.get_queue_status()
            current_running = queue_status['current_running']
            current_running_count = process_running_counts.get(current_pid, 0)
            # 使用队列状态和数据库状态中的较大值
            actual_running = max(current_running, current_running_count)
            
            # 如果只有一个进程，允许所有任务在这个进程执行（可以并发）
            # 即使达到上限，也允许排队等待，确保所有任务都能执行
            if len(all_processes) == 1:
                logger.info(
                    f"任务 '{task_name}' 分配给当前进程 {current_pid} "
                    f"（单进程环境，相同cron的任务可以并发执行，"
                    f"当前运行: {actual_running}/{max_concurrent}）"
                )
                return True, current_pid  # 单进程环境，允许排队等待
            
            if actual_running < max_concurrent:
                logger.debug(
                    f"任务 '{task_name}' 分配给当前进程 {current_pid} "
                    f"（轮询分配，当前运行: {actual_running}/{max_concurrent}）"
                )
                return True, current_pid
            else:
                # 当前进程已满载，查找其他空闲进程
                for pid in all_processes:
                    if pid != current_pid:
                        pid_running = process_running_counts.get(pid, 0)
                        # 假设其他进程也有相同的max_concurrent限制
                        if pid_running < max_concurrent:
                            logger.info(
                                f"任务 '{task_name}' 当前进程 {current_pid} 已满载 "
                                f"（运行: {actual_running}/{max_concurrent}），"
                                f"分配给其他进程 {pid}（运行: {pid_running}/{max_concurrent}）"
                            )
                            return False, pid
                
                # 所有进程都满载，使用当前进程（排队）
                logger.warning(
                    f"任务 '{task_name}' 所有进程都已满载，"
                    f"将在当前进程 {current_pid} 排队等待"
                )
                return True, current_pid
        else:
            # 分配给了其他进程，当前进程应该跳过
            logger.debug(
                f"任务 '{task_name}' 已分配给进程 {assigned_pid} "
                f"（轮询分配），当前进程 {current_pid} 跳过执行"
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
    if assigned_pid == CURRENT_PID:
        return True
    
    # 分配给了其他进程，当前进程应该跳过
    logger.debug(
        f"任务 '{task_name}' 已分配给进程 {assigned_pid}，"
        f"当前进程 {CURRENT_PID} 跳过执行"
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
    
    # 将任务添加到当前进程的任务列表
    if CURRENT_PID not in _process_task_assignments:
        _process_task_assignments[CURRENT_PID] = []
    
    if task_name not in _process_task_assignments[CURRENT_PID]:
        _process_task_assignments[CURRENT_PID].append(task_name)
    
    # 将当前进程添加到该cron表达式的进程组
    if cron_hash not in _cron_process_groups:
        _cron_process_groups[cron_hash] = []
    
    if CURRENT_PID not in _cron_process_groups[cron_hash]:
        _cron_process_groups[cron_hash].append(CURRENT_PID)
    
    logger.debug(
        f"任务 '{task_name}' (Cron: {cron_expression}) "
        f"已注册到进程 {CURRENT_PID}"
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

