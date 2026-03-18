"""
定时任务模块
独立的任务调度模块，包含调度器、锁机制、任务注册等功能
"""

from .lock import (
    acquire_task_lock,
    release_task_lock,
    CURRENT_PID,
    CURRENT_HOST,
)
from .scheduler import (
    get_scheduler,
    init_scheduled_tasks,
    start_scheduler,
    shutdown_scheduler,
    register_scheduled_task,
    execute_task_with_lock,
)
from .task_registry import (
    register_task_function,
    get_task_function,
    get_task_function_by_name_or_path,
    load_function_by_path,
    get_task_function_info,
    get_all_registered_tasks,
    auto_register_tasks,
)
