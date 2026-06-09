"""
定时任务执行结果暂存（进程内内存）。

功能说明：
- 任务完成后将摘要写入模块级字典，供 get_task_result 读取
- 管理端同步到 scheduled_tasks.last_error 等字段展示

在系统中的位置：
- 被各 tasks/*.py 在成功/失败时 set_task_result

注意事项：
1. 多进程间不共享，仅当前 worker 可见；重启后丢失，以 DB 同步字段为准
2. 勿存放敏感信息或大对象，仅保存人类可读的简短摘要
"""
from typing import Dict, Optional

_task_results: Dict[str, str] = {}


def get_task_result(task_name: str) -> Optional[str]:
    """读取指定任务最近一次执行结果摘要，未执行过返回 None。"""
    return _task_results.get(task_name)


def set_task_result(task_name: str, result: str) -> None:
    """覆盖写入任务执行结果（成功/跳过/失败消息）。"""
    _task_results[task_name] = result


def clear_task_result(task_name: str) -> None:
    """清除某任务的结果缓存（任务重跑前可选调用）。"""
    _task_results.pop(task_name, None)
