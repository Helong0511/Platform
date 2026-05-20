"""
定时任务执行结果暂存（写入 scheduled_tasks.last_error 等）。
"""
from typing import Dict, Optional

_task_results: Dict[str, str] = {}


def get_task_result(task_name: str) -> Optional[str]:
    return _task_results.get(task_name)


def set_task_result(task_name: str, result: str) -> None:
    _task_results[task_name] = result


def clear_task_result(task_name: str) -> None:
    _task_results.pop(task_name, None)
