"""
Asone 上游广告数据拉取定时任务。

功能说明：
- 从 Asone（asone.club）渠道报表 API 拉取明细/国家/广告位/日报
- 默认拉取明细（channel-data-report，平台 cross 维度）；其它维度由环境变量开关
- 经字段类型规范化、国家名别名与去重写入 ad_data

鉴权：Header X-API-Key
文档：https://s.apifox.cn/57980c06-f0c6-4e22-b6c1-1524be28b003
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.ad_data_metadata import (
    DATA_SOURCE_ASONE,
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_CROSS,
    REPORT_TYPE_DAILY,
    REPORT_TYPE_UNIT,
)
from app.core.config import settings
from app.scheduler_module.asone_normalize import make_asone_transform
from app.scheduler_module.task_names import ASONE_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import log_scheduled_task_skip, resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import (
    ASONE_PATH_COUNTRY,
    ASONE_PATH_DAILY,
    ASONE_PATH_DETAIL,
    ASONE_PATH_UNIT,
    fetch_asone_rows,
)
from app.scheduler_module.upstream_http import UpstreamTransientError
from app.scheduler_module.upstream_task_runner import (
    UpstreamTaskOutcome,
    run_upstream_import_task,
)

logger = logging.getLogger(__name__)

# 规范化后稳定字段 → 平台标准字段（normalize 已写成同名）
ASONE_COMMON_FIELD_MAPPING: dict[str, str] = {
    "date": "date",
    "product_name": "product_name",
    "request_count": "request_count",
    "match_count": "match_count",
    "display_count": "display_count",
    "click_count": "click_count",
    "revenue_before_deduct": "revenue_before_deduct",
    "ecpm_before_deduct": "ecpm_before_deduct",
}

ASONE_DETAIL_FIELD_MAPPING: dict[str, str] = {
    **ASONE_COMMON_FIELD_MAPPING,
    "country_code": "country_code",
    "ad_unit": "ad_unit",
}

ASONE_COUNTRY_FIELD_MAPPING: dict[str, str] = {
    **ASONE_COMMON_FIELD_MAPPING,
    "country_code": "country_code",
}

ASONE_UNIT_FIELD_MAPPING: dict[str, str] = {
    **ASONE_COMMON_FIELD_MAPPING,
    "ad_unit": "ad_unit",
}

ASONE_DAILY_FIELD_MAPPING: dict[str, str] = dict(ASONE_COMMON_FIELD_MAPPING)

_ASONE_REPORTS: list[dict[str, Any]] = [
    {
        "env_flag": "ASONE_API_FETCH_DETAIL",
        "path": ASONE_PATH_DETAIL,
        "label": "Asone detail(cross)",
        "mapping": ASONE_DETAIL_FIELD_MAPPING,
        "report_type": REPORT_TYPE_CROSS,
    },
    {
        "env_flag": "ASONE_API_FETCH_COUNTRY",
        "path": ASONE_PATH_COUNTRY,
        "label": "Asone country",
        "mapping": ASONE_COUNTRY_FIELD_MAPPING,
        "report_type": REPORT_TYPE_COUNTRY,
    },
    {
        "env_flag": "ASONE_API_FETCH_UNIT",
        "path": ASONE_PATH_UNIT,
        "label": "Asone unit",
        "mapping": ASONE_UNIT_FIELD_MAPPING,
        "report_type": REPORT_TYPE_UNIT,
    },
    {
        "env_flag": "ASONE_API_FETCH_DAILY",
        "path": ASONE_PATH_DAILY,
        "label": "Asone daily",
        "mapping": ASONE_DAILY_FIELD_MAPPING,
        "report_type": REPORT_TYPE_DAILY,
    },
]


def _is_report_enabled(flag: str) -> bool:
    return bool(getattr(settings, flag, False))


async def asone_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Asone 定时拉数：按配置维度拉取报表并去重入库。"""
    base_url = settings.ASONE_API_BASE_URL
    api_key = settings.ASONE_API_KEY

    if not api_key or not str(api_key).strip():
        skip_msg = "跳过: Asone API 未配置（请在 .env 设置 ASONE_API_KEY）"
        logger.warning(skip_msg)
        set_task_result(ASONE_API_TASK_NAME, skip_msg)
        return

    as_start, as_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_params = {"起始日期": as_start, "终止日期": as_end}

    enabled_reports = [r for r in _ASONE_REPORTS if _is_report_enabled(r["env_flag"])]
    if not enabled_reports:
        skip_msg = (
            "跳过: Asone 未开启任何报表维度"
            "（ASONE_API_FETCH_DETAIL / COUNTRY / UNIT / DAILY 均为 false）"
        )
        logger.warning(skip_msg)
        set_task_result(ASONE_API_TASK_NAME, skip_msg)
        return

    summaries: list[str] = []
    transient_errors: list[str] = []
    hard_errors: list[str] = []

    for report in enabled_reports:
        report_label = report["label"]
        report_type = report["report_type"]
        try:

            async def _make_fetch(
                p=report["path"],
                lb=report_label,
            ):
                return await fetch_asone_rows(
                    base_url=base_url,
                    api_key=api_key,
                    start=as_start,
                    end=as_end,
                    path=p,
                    label=lb,
                    page_size=settings.ASONE_API_PAGE_SIZE,
                )

            outcome = await run_upstream_import_task(
                ASONE_API_TASK_NAME,
                credentials=None,
                fetch_data=_make_fetch,
                field_mapping=report["mapping"],
                source="Asone定时任务",
                notify_title=f"Asone ({report_label.split()[-1]})",
                data_transform=make_asone_transform(report_type),
                data_source=DATA_SOURCE_ASONE,
                report_type=report_type,
                log_label=report_label,
                notify_params=notify_params,
            )
            if outcome == UpstreamTaskOutcome.SUCCESS:
                summaries.append(f"{report_label}: 成功")
            elif outcome == UpstreamTaskOutcome.SKIPPED_TRANSIENT:
                transient_errors.append(f"{report_label}: 上游暂时不可达")
            else:
                transient_errors.append(f"{report_label}: 已跳过({outcome.value})")
        except UpstreamTransientError as exc:
            transient_errors.append(f"{report_label}: 上游暂时不可达")
            logger.warning("Asone 报表瞬时故障 - %s: %s", report_label, exc)
        except Exception as exc:
            err = f"{report_label}: {exc}"
            hard_errors.append(err)
            logger.error("Asone 报表拉数失败 - %s", err)

    if hard_errors and not summaries and not transient_errors:
        msg = f"执行失败: {'; '.join(hard_errors)}"
        set_task_result(ASONE_API_TASK_NAME, msg)
        raise RuntimeError(msg)

    if hard_errors:
        msg = (
            f"部分失败: {'; '.join(hard_errors)}"
            + (f" | 软跳过: {'; '.join(transient_errors)}" if transient_errors else "")
            + (f" | 成功: {'; '.join(summaries)}" if summaries else "")
        )
        set_task_result(ASONE_API_TASK_NAME, msg)
        raise RuntimeError(msg)

    if transient_errors and not summaries:
        soft_msg = f"软跳过: 上游暂时不可达，等待下次调度 | {'; '.join(transient_errors)}"
        logger.warning("[%s] %s", ASONE_API_TASK_NAME, soft_msg)
        log_scheduled_task_skip(
            ASONE_API_TASK_NAME, "上游网络瞬时故障", detail="; ".join(transient_errors)
        )
        set_task_result(ASONE_API_TASK_NAME, soft_msg)
        return

    if transient_errors and summaries:
        msg = (
            f"部分跳过(上游暂时不可达): {'; '.join(transient_errors)} "
            f"| 成功: {'; '.join(summaries)}"
        )
        logger.warning("[%s] %s", ASONE_API_TASK_NAME, msg)
        set_task_result(ASONE_API_TASK_NAME, msg)
        return

    set_task_result(ASONE_API_TASK_NAME, "执行成功: " + "; ".join(summaries))
