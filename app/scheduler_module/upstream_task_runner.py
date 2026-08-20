"""
上游广告数据拉取任务公共执行骨架。

职责：凭证校验、任务开始日志、拉数回调、标准入库与统一异常记录。
各 tasks/*.py 仅需提供 fetch_data 闭包与字段映射表。
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from enum import Enum
from typing import Any, Optional, Union

from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    get_current_time_str,
    log_scheduled_task_skip,
    log_task_start,
    upstream_credential_missing,
)
from app.scheduler_module.upstream_fetch import UpstreamFetchResult, unwrap_upstream_fetch_result
from app.scheduler_module.upstream_http import UpstreamTransientError
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

DataTransform = Optional[Callable[[list], list]]


class UpstreamTaskOutcome(str, Enum):
    """run_upstream_import_task 执行结果（避免用 bool/文案猜测）。"""

    SUCCESS = "success"
    SKIPPED_CONFIG = "skipped_config"
    SKIPPED_TRANSIENT = "skipped_transient"


async def run_upstream_import_task(
    task_name: str,
    *,
    fetch_data: Callable[[], Awaitable[Union[UpstreamFetchResult, list[Any]]]],
    field_mapping: dict[str, str],
    source: str,
    notify_title: str,
    credentials: Optional[tuple[Optional[str], ...]] = None,
    skip_hint: str = "",
    data_transform: DataTransform = None,
    log_label: Optional[str] = None,
    notify_params: Optional[Mapping[str, Any]] = None,
    data_source: str = "unknown",
    report_type: str = "legacy",
    upstream_account: str = "",
) -> UpstreamTaskOutcome:
    """
    上游拉数任务标准流程：未配置则跳过 → 拉数 → import_upstream_ad_data 入库。

    report_type 应由调用方显式传入（多维度任务必须传）；仅单维度任务可留空走
    infer_report_type_from_shape 自动推断。

    上游超时/连不上（``UpstreamTransientError``）时软跳过：写入结果说明、不抛异常、
    不按程序崩溃告警，等待下次 cron 自动重试。

    Returns:
        UpstreamTaskOutcome：SUCCESS / SKIPPED_CONFIG / SKIPPED_TRANSIENT
    """
    if credentials is not None and upstream_credential_missing(*credentials):
        logger.warning(skip_hint)
        set_task_result(task_name, skip_hint)
        return UpstreamTaskOutcome.SKIPPED_CONFIG

    current_time_str = get_current_time_str()
    log_task_start(task_name)
    label = log_label or task_name

    try:
        fetch_result = await fetch_data()
        data, fetch_stats = unwrap_upstream_fetch_result(fetch_result)
        await import_upstream_ad_data(
            task_name=task_name,
            data=data,
            field_mapping=field_mapping,
            source=source,
            current_time_str=current_time_str,
            notify_title=notify_title,
            data_transform=data_transform,
            notify_params=notify_params,
            fetch_stats=fetch_stats,
            data_source=data_source,
            report_type=report_type,
            upstream_account=upstream_account,
        )
        return UpstreamTaskOutcome.SUCCESS
    except UpstreamTransientError as e:
        # 上游不可达：已 HTTP 重试耗尽；软跳过，避免「程序运行错误」刷屏
        soft_msg = f"软跳过: 上游暂时不可达，等待下次调度 | {e}"
        logger.warning("[%s] %s", label, soft_msg)
        log_scheduled_task_skip(task_name, "上游网络瞬时故障", detail=str(e))
        set_task_result(task_name, soft_msg)
        return UpstreamTaskOutcome.SKIPPED_TRANSIENT
    except Exception as e:
        # 不带 exc_info：调度器会统一 log_scheduled_task_failure(exc_info=True)，避免双份 Telegram
        error_msg = f"{task_name} 执行失败: {str(e)}"
        logger.error(error_msg)
        logger.warning("[%s] %s", label, error_msg)
        raise
