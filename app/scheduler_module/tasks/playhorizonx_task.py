"""
PlayHorizonx 上游广告数据拉取定时任务。

功能说明：
- 从 PlayHorizonx（api.h5gamegl.top）API 获取上游报表数据
- 接口 POST /reports/index，md5 签名鉴权
- 默认按 unit 维度入库；可开启 cross 维度（同一接口数据，入库维度不同）
- 经字段映射与去重写入 ad_data 表

接口文档：PlayHorizonx API Report Query v1.0
鉴权方式：Header sign（md5(username + startDate + endDate + private_key)）
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.ad_data_metadata import (
    DATA_SOURCE_PLAYHORIZONX,
    REPORT_TYPE_CROSS,
    REPORT_TYPE_UNIT,
)
from app.core.config import settings
from app.scheduler_module.task_names import PLAYHORIZONX_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.upstream_fetch import (
    fetch_playhorizonx_rows,
)
from app.scheduler_module.upstream_task_runner import (
    UpstreamTaskOutcome,
    run_upstream_import_task,
)
from app.scheduler_module.task_utils import log_scheduled_task_skip, resolve_upstream_date_range

logger = logging.getLogger(__name__)

# PlayHorizonx /reports/index 字段映射（响应字段 → 平台 ad_data 字段）
# 响应含：date、url、com_name、requests、matched_queries、viewsCount、clicks、channel_revenue
# 无 country 字段
# unit 维度：按广告单元入库（国家为 ZZ）
# cross 维度：同接口数据，若后续上游增加 country 字段则按 cross 入库
PLAYHORIZONX_FIELD_MAPPING: dict[str, str] = {
    "date": "date",
    "product_name": "url",
    "ad_unit": "com_name",
    "request_count": "requests",
    "match_count": "matched_queries",
    "display_count": "viewsCount",
    "click_count": "clicks",
    "revenue_before_deduct": "channel_revenue",
}

# 报表维度配置
_PLAYHORIZONX_REPORTS: list[dict[str, Any]] = [
    {
        "env_flag": "PLAYHORIZONX_API_FETCH_UNIT",
        "label": "PlayHorizonx /reports/index (unit)",
        "mapping": PLAYHORIZONX_FIELD_MAPPING,
        "report_type": REPORT_TYPE_UNIT,
    },
    {
        "env_flag": "PLAYHORIZONX_API_FETCH_CROSS",
        "label": "PlayHorizonx /reports/index (cross)",
        "mapping": PLAYHORIZONX_FIELD_MAPPING,
        "report_type": REPORT_TYPE_CROSS,
    },
]


def _is_report_enabled(flag: str) -> bool:
    return getattr(settings, flag, False)


async def playhorizonx_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """PlayHorizonx 定时拉数任务：按配置维度拉取报表并去重入库。"""
    base_url = settings.PLAYHORIZONX_API_BASE_URL
    username = settings.PLAYHORIZONX_API_USERNAME
    private_key = settings.PLAYHORIZONX_API_PRIVATE_KEY

    if not username or not username.strip():
        skip_msg = "跳过: PlayHorizonx API 未配置（请在 .env 设置 PLAYHORIZONX_API_USERNAME）"
        logger.warning(skip_msg)
        set_task_result(PLAYHORIZONX_API_TASK_NAME, skip_msg)
        return

    if not private_key or not private_key.strip():
        skip_msg = "跳过: PlayHorizonx API 未配置（请在 .env 设置 PLAYHORIZONX_API_PRIVATE_KEY）"
        logger.warning(skip_msg)
        set_task_result(PLAYHORIZONX_API_TASK_NAME, skip_msg)
        return

    ph_start, ph_end = resolve_upstream_date_range(
        start_date, end_date, early_morning_dual_day=True,
    )
    notify_params = {"起始日期": ph_start, "终止日期": ph_end}

    enabled_reports = [r for r in _PLAYHORIZONX_REPORTS if _is_report_enabled(r["env_flag"])]
    if not enabled_reports:
        skip_msg = "跳过: PlayHorizonx 未开启任何维度（PLAYHORIZONX_API_FETCH_UNIT/CROSS 均为 false）"
        logger.warning(skip_msg)
        set_task_result(PLAYHORIZONX_API_TASK_NAME, skip_msg)
        return

    summaries: list[str] = []
    transient_errors: list[str] = []
    hard_errors: list[str] = []

    for report in enabled_reports:
        report_label = report["label"]
        try:
            async def _make_fetch(lb=report_label):
                return await fetch_playhorizonx_rows(
                    base_url=base_url,
                    username=username,
                    private_key=private_key,
                    start_date=ph_start,
                    end_date=ph_end,
                    label=lb,
                )

            outcome = await run_upstream_import_task(
                PLAYHORIZONX_API_TASK_NAME,
                credentials=(username, private_key),
                fetch_data=_make_fetch,
                field_mapping=report["mapping"],
                source="PlayHorizonx定时任务",
                notify_title=f"PlayHorizonx ({report_label.split()[-1].strip('()')})",
                data_source=DATA_SOURCE_PLAYHORIZONX,
                report_type=report["report_type"],
                log_label=report_label,
                notify_params=notify_params,
            )

            if outcome == UpstreamTaskOutcome.SUCCESS:
                summaries.append(f"{report_label}: 成功")
            elif outcome == UpstreamTaskOutcome.SKIPPED_TRANSIENT:
                transient_errors.append(f"{report_label}: 上游暂时不可达")
            else:
                transient_errors.append(f"{report_label}: 已跳过({outcome.value})")
        except Exception as exc:
            err = f"{report_label}: {exc}"
            hard_errors.append(err)
            logger.error("PlayHorizonx 报表拉数失败 - %s", err)

    if hard_errors and not summaries and not transient_errors:
        msg = f"执行失败: {'; '.join(hard_errors)}"
        set_task_result(PLAYHORIZONX_API_TASK_NAME, msg)
        raise RuntimeError(msg)

    if hard_errors:
        msg = (
            f"部分失败: {'; '.join(hard_errors)}"
            + (f" | 软跳过: {'; '.join(transient_errors)}" if transient_errors else "")
            + (f" | 成功: {'; '.join(summaries)}" if summaries else "")
        )
        set_task_result(PLAYHORIZONX_API_TASK_NAME, msg)
        raise RuntimeError(msg)

    if transient_errors and not summaries:
        soft_msg = f"软跳过: 上游暂时不可达，等待下次调度 | {'; '.join(transient_errors)}"
        logger.warning("[%s] %s", PLAYHORIZONX_API_TASK_NAME, soft_msg)
        log_scheduled_task_skip(
            PLAYHORIZONX_API_TASK_NAME, "上游网络瞬时故障", detail="; ".join(transient_errors)
        )
        set_task_result(PLAYHORIZONX_API_TASK_NAME, soft_msg)
        return

    if transient_errors and summaries:
        msg = (
            f"部分跳过(上游暂时不可达): {'; '.join(transient_errors)} "
            f"| 成功: {'; '.join(summaries)}"
        )
        logger.warning("[%s] %s", PLAYHORIZONX_API_TASK_NAME, msg)
        set_task_result(PLAYHORIZONX_API_TASK_NAME, msg)
        return

    set_task_result(PLAYHORIZONX_API_TASK_NAME, "执行成功: " + "; ".join(summaries))
