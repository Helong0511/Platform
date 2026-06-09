"""
定时任务调度子系统包。

功能说明：
- 导出调度器生命周期（init/start/shutdown）、分布式锁、任务注册与执行入口
- 基于 APScheduler + 数据库行锁，支持多 worker 部署下单次执行

在系统中的位置：
- 由 ``app.main`` lifespan 启动；任务定义在 ``tasks/``，配置在 ``task_config.py``

注意事项：
1. 新增任务须同时在 task_config.py、task_names.py 与 tasks 模块中注册
2. 长耗时任务应通过 task_queue 限制并发，避免拖垮事件循环
"""

from .lock import (
    acquire_task_lock,
    release_task_lock,
    get_current_pid,
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
