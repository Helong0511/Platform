"""
定时任务执行队列管理器
用于限制同时执行的任务数量，避免资源竞争和性能问题

功能：
1. 限制并发任务数量
2. 支持任务优先级
3. 任务排队等待执行
4. 防止同一进程同时执行过多任务
"""
import asyncio
import logging
from typing import Optional, Callable, Any, Dict
from datetime import datetime, timezone
from collections import deque
from enum import IntEnum

from app.core.config import settings

logger = logging.getLogger(__name__)


class TaskPriority(IntEnum):
    """任务优先级枚举"""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    CRITICAL = 0  # 最高优先级


class TaskQueue:
    """
    任务执行队列管理器
    
    功能：
    - 限制同时执行的任务数量
    - 支持任务优先级
    - 任务排队等待执行
    """
    
    def __init__(self, max_concurrent_tasks: int = 1):
        """
        初始化任务队列
        
        Args:
            max_concurrent_tasks: 最大并发任务数（默认1，即同一时间只执行一个任务）
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.current_running = 0  # 当前正在执行的任务数
        self.queue: deque = deque()  # 任务队列（按优先级排序）
        self.lock = asyncio.Lock()  # 队列操作锁
        self.running_tasks: Dict[str, asyncio.Task] = {}  # 正在执行的任务字典
        
    async def submit(
        self,
        task_name: str,
        task_func: Callable[..., Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        *args: Any,
        **kwargs: Any
    ) -> None:
        """
        提交任务到队列
        
        Args:
            task_name: 任务名称
            task_func: 任务函数（可以是同步或异步函数，也可以是协程对象）
            priority: 任务优先级（默认NORMAL）
            *args: 任务函数位置参数（如果task_func是协程对象，则忽略）
            **kwargs: 任务函数关键字参数（如果task_func是协程对象，则忽略）
        """
        async with self.lock:
            # 如果当前运行的任务数小于最大值，直接执行
            if self.current_running < self.max_concurrent_tasks:
                can_execute_immediately = True
                self.current_running += 1
                # 创建并执行任务（在锁外执行，避免长时间持有锁）
                task = asyncio.create_task(
                    self._execute_task(task_name, task_func, *args, **kwargs)
                )
                self.running_tasks[task_name] = task
                logger.debug(
                    f"任务 '{task_name}' 立即并发执行 "
                    f"（当前运行: {self.current_running}/{self.max_concurrent_tasks}，"
                    f"队列: {len(self.queue)}）"
                )
            else:
                # 任务需要排队等待
                self.queue.append({
                    'task_name': task_name,
                    'task_func': task_func,
                    'priority': priority,
                    'args': args,
                    'kwargs': kwargs,
                    'submitted_at': datetime.now(timezone.utc)
                })
                logger.info(
                    f"任务 '{task_name}' 已加入队列等待执行 "
                    f"（队列长度: {len(self.queue)}, 当前运行: {self.current_running}/{self.max_concurrent_tasks}）"
                )
    
    async def _execute_task(
        self,
        task_name: str,
        task_func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> None:
        """
        执行任务（内部方法）
        
        Args:
            task_name: 任务名称
            task_func: 任务函数（可以是协程函数、普通函数或协程对象）
            *args: 任务函数位置参数
            **kwargs: 任务函数关键字参数
        """
        try:
            # 执行任务
            if asyncio.iscoroutine(task_func):
                # task_func 是协程对象，直接 await
                await task_func
            elif asyncio.iscoroutinefunction(task_func):
                # task_func 是协程函数，调用并 await
                await task_func(*args, **kwargs)
            elif callable(task_func):
                # task_func 是普通函数，在线程池中执行
                await asyncio.to_thread(task_func, *args, **kwargs)
            else:
                logger.error(f"任务 '{task_name}' 的 task_func 类型无效: {type(task_func)}")
        except Exception as e:
            logger.error(f"任务 '{task_name}' 执行出错: {e}", exc_info=True)
        finally:
            # 任务执行完成，从运行列表中移除
            async with self.lock:
                self.current_running -= 1
                if task_name in self.running_tasks:
                    del self.running_tasks[task_name]
                
                # 尝试执行队列中的下一个任务
                await self._process_queue()
    
    async def _process_queue(self) -> None:
        """
        处理队列中的任务（内部方法）
        从队列中取出优先级最高的任务执行
        """
        if not self.queue:
            return
        
        if self.current_running >= self.max_concurrent_tasks:
            return
        
        # 按优先级排序队列（优先级数字越小，优先级越高）
        sorted_queue = sorted(
            self.queue,
            key=lambda x: (x['priority'], x['submitted_at'])
        )
        
        # 取出优先级最高的任务
        task_item = sorted_queue[0]
        self.queue.remove(task_item)
        
        task_name = task_item['task_name']
        task_func = task_item['task_func']
        args = task_item['args']
        kwargs = task_item['kwargs']
        
        # 更新运行计数
        self.current_running += 1
        
        # 计算等待时间
        wait_time = (datetime.now(timezone.utc) - task_item['submitted_at']).total_seconds()
        logger.info(
            f"任务 '{task_name}' 从队列中取出并发执行 "
            f"（等待时间: {wait_time:.2f}秒, 当前运行: {self.current_running}/{self.max_concurrent_tasks}，"
            f"剩余队列: {len(self.queue)}）"
        )
        
        # 创建并执行任务
        task = asyncio.create_task(
            self._execute_task(task_name, task_func, *args, **kwargs)
        )
        self.running_tasks[task_name] = task
    
    async def wait_for_completion(self, timeout: Optional[float] = None) -> None:
        """
        等待所有任务完成
        
        Args:
            timeout: 超时时间（秒），None表示无限等待
        """
        if timeout:
            await asyncio.wait_for(
                self._wait_all_tasks(),
                timeout=timeout
            )
        else:
            await self._wait_all_tasks()
    
    async def _wait_all_tasks(self) -> None:
        """等待所有任务完成（内部方法）"""
        while True:
            async with self.lock:
                if self.current_running == 0 and len(self.queue) == 0:
                    break
            await asyncio.sleep(0.1)
        
        # 等待所有运行中的任务完成
        if self.running_tasks:
            await asyncio.gather(*self.running_tasks.values(), return_exceptions=True)
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """
        获取队列状态（异步方法）
        
        Returns:
            包含队列状态的字典：
            - current_running: 当前正在执行的任务数
            - max_concurrent: 最大并发任务数
            - queue_length: 队列中等待的任务数
            - running_tasks: 正在执行的任务名称列表
            - queued_tasks: 队列中等待的任务名称列表（按优先级排序）
            - queue_details: 队列详细信息（包含优先级和等待时间）
        """
        async with self.lock:
            now = datetime.now(timezone.utc)
            queue_details = []
            for item in self.queue:
                wait_time = (now - item['submitted_at']).total_seconds()
                queue_details.append({
                    'task_name': item['task_name'],
                    'priority': item['priority'].name if isinstance(item['priority'], TaskPriority) else str(item['priority']),
                    'priority_value': item['priority'].value if isinstance(item['priority'], TaskPriority) else item['priority'],
                    'wait_time_seconds': round(wait_time, 2),
                    'submitted_at': item['submitted_at'].isoformat()
                })
            
            # 按优先级和提交时间排序
            queue_details.sort(key=lambda x: (x['priority_value'], x['submitted_at']))
            
            return {
                'current_running': self.current_running,
                'max_concurrent': self.max_concurrent_tasks,
                'queue_length': len(self.queue),
                'running_tasks': list(self.running_tasks.keys()),
                'queued_tasks': [item['task_name'] for item in self.queue],
                'queue_details': queue_details
            }


# 全局任务队列实例
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """
    获取全局任务队列实例（单例模式）
    
    Returns:
        TaskQueue: 任务队列实例
    """
    global _task_queue
    if _task_queue is None:
        max_concurrent = getattr(settings, 'MAX_CONCURRENT_SCHEDULED_TASKS', 1)
        _task_queue = TaskQueue(max_concurrent_tasks=max_concurrent)
        logger.info(
            f"任务队列已初始化（最大并发数: {max_concurrent}）"
        )
    return _task_queue


async def submit_task_to_queue(
    task_name: str,
    task_func: Callable[..., Any],
    priority: TaskPriority = TaskPriority.NORMAL,
    *args: Any,
    **kwargs: Any
) -> None:
    """
    提交任务到队列（便捷函数）
    
    Args:
        task_name: 任务名称
        task_func: 任务函数
        priority: 任务优先级（默认NORMAL）
        *args: 任务函数位置参数
        **kwargs: 任务函数关键字参数
    """
    queue = get_task_queue()
    await queue.submit(task_name, task_func, priority, *args, **kwargs)

