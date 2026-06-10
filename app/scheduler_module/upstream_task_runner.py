"""
上游广告数据拉取任务公共执行骨架。

职责：凭证校验、任务开始日志、拉数回调、标准入库与统一异常记录。
各 tasks/*.py 仅需提供 fetch_data 闭包与字段映射表。
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    get_current_time_str,
    log_task_start,
    upstream_credential_missing,
)
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

DataTransform = Optional[Callable[[list], list]]


async def run_upstream_import_task(
    task_name: str,
    *,
    fetch_data: Callable[[], Awaitable[list[Any]]],
    field_mapping: dict[str, str],
    source: str,
    notify_title: str,
    credentials: Optional[tuple[Optional[str], ...]] = None,
    skip_hint: str = "",
    data_transform: DataTransform = None,
    log_label: Optional[str] = None,
) -> None:
    """
    上游拉数任务标准流程：未配置则跳过 → 拉数 → import_upstream_ad_data 入库。

    参数:
        task_name: 调度任务名（与 task_names 常量一致）
        credentials: 上游凭证元组，任一为空则跳过；为 None 时跳过凭证校验（调用方已校验）
        skip_hint: 跳过时的说明（写入 task_result）
        fetch_data: 异步拉数函数，返回原始行列表
        field_mapping: 平台字段 → 上游字段映射
        source: 入库来源标识
        notify_title: Telegram 通知标题
        data_transform: 入库前可选预处理（就地修改列表）
        log_label: 错误日志中的业务标签，默认等于 task_name
    """
    if credentials is not None and upstream_credential_missing(*credentials):
        logger.warning(skip_hint)
        set_task_result(task_name, skip_hint)
        return

    current_time_str = get_current_time_str()
    log_task_start(task_name)

    try:
        data = await fetch_data()
        await import_upstream_ad_data(
            task_name=task_name,
            data=data,
            field_mapping=field_mapping,
            source=source,
            current_time_str=current_time_str,
            notify_title=notify_title,
            data_transform=data_transform,
        )
    except Exception as e:
        label = log_label or task_name
        error_msg = f"{task_name} 执行失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.warning(f"[{label}] {error_msg}")
        raise
