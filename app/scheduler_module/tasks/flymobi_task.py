"""
FlyMobi 上游广告数据拉取定时任务。

功能说明：
- 从 FlyMobi（ads.gofinds.xyz）API 获取 Ad Manager 报表数据
- 默认拉取 countryList（国家报表），可通过环境变量开启 adUnitList / dayList
- 经字段映射与去重写入 ad_data 表

接口文档：https://ads.gofinds.xyz/avatar/2025/12/05/api_v1.0.html
鉴权方式：Bearer Token（API 访问令牌）
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.ad_data_metadata import DATA_SOURCE_FLYMOBI
from app.core.config import settings
from app.scheduler_module.task_names import FLYMOBI_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.upstream_fetch import (
    fetch_flymobi_rows,
)
from app.scheduler_module.upstream_task_runner import (
    UpstreamTaskOutcome,
    run_upstream_import_task,
)
from app.scheduler_module.task_utils import log_scheduled_task_skip, resolve_upstream_date_range

logger = logging.getLogger(__name__)

# ── 接口路径 ──
FLYMOBI_PATH_COUNTRY = "/api/google/adManager/countryList"
FLYMOBI_PATH_UNIT = "/api/google/adManager/adUnitList"
FLYMOBI_PATH_DAILY = "/api/google/adManager/dayList"

# ── 字段映射（FlyMobi API 响应字段 → 平台 ad_data 字段）──
# countryList 响应含 countryCode + adUnitName
FLYMOBI_COUNTRY_FIELD_MAPPING: dict[str, str] = {
    "date": "date",
    "product_name": "site",
    "ad_unit": "adUnitName",
    "country_code": "country_code_resolved",
    "request_count": "totalRequests",
    "match_count": "matchingRequests",
    "display_count": "impressions",
    "click_count": "clicks",
    "click_rate": "ctr",
    "coverage_rate": "matchRate",
    "cpc": "cpc",
    "ecpm_before_deduct": "averageEcpm",
    "revenue_before_deduct": "revenue",
    "pageviews": "viewableImpressions",
}

# adUnitList 响应含 adUnitName，无 countryCode
FLYMOBI_UNIT_FIELD_MAPPING: dict[str, str] = {
    "date": "date",
    "product_name": "site",
    "ad_unit": "adUnitName",
    "request_count": "totalRequests",
    "match_count": "matchingRequests",
    "display_count": "impressions",
    "click_count": "clicks",
    "click_rate": "ctr",
    "coverage_rate": "matchRate",
    "cpc": "cpc",
    "ecpm_before_deduct": "averageEcpm",
    "revenue_before_deduct": "revenue",
    "pageviews": "viewableImpressions",
}

# dayList 响应无 adUnitName / countryCode
FLYMOBI_DAILY_FIELD_MAPPING: dict[str, str] = {
    "date": "date",
    "product_name": "site",
    "request_count": "totalRequests",
    "match_count": "matchingRequests",
    "display_count": "impressions",
    "click_count": "clicks",
    "click_rate": "ctr",
    "coverage_rate": "matchRate",
    "cpc": "cpc",
    "ecpm_before_deduct": "averageEcpm",
    "revenue_before_deduct": "revenue",
    "pageviews": "viewableImpressions",
}

# 报表维度配置
_FLYMOBI_REPORTS: list[dict[str, Any]] = [
    {
        "env_flag": "FLYMOBI_API_FETCH_COUNTRY",
        "path": FLYMOBI_PATH_COUNTRY,
        "label": "FlyMobi countryList",
        "mapping": FLYMOBI_COUNTRY_FIELD_MAPPING,
    },
    {
        "env_flag": "FLYMOBI_API_FETCH_UNIT",
        "path": FLYMOBI_PATH_UNIT,
        "label": "FlyMobi adUnitList",
        "mapping": FLYMOBI_UNIT_FIELD_MAPPING,
    },
    {
        "env_flag": "FLYMOBI_API_FETCH_DAILY",
        "path": FLYMOBI_PATH_DAILY,
        "label": "FlyMobi dayList",
        "mapping": FLYMOBI_DAILY_FIELD_MAPPING,
    },
]


def _is_report_enabled(flag: str) -> bool:
    return getattr(settings, flag, False)


def preprocess_flymobi_country_rows(ad_data: list[Any]) -> list[Any]:
    """
    预处理 FlyMobi 国家字段，统一转成平台可识别输入。

    规则：
    1. 优先使用 countryCode，并去空格后转大写
    2. countryCode 缺失时回退 countryName，让平台统一国家识别逻辑继续解析
    3. 两者都缺失时保留空串，最终按“无国家”处理
    """
    for item in ad_data:
        raw_code = str(item.get("countryCode") or "").strip()
        raw_name = str(item.get("countryName") or "").strip()
        if raw_code:
            item["country_code_resolved"] = raw_code.upper()
        elif raw_name:
            item["country_code_resolved"] = raw_name
        else:
            item["country_code_resolved"] = ""
    return ad_data


async def flymobi_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """FlyMobi 定时拉数任务：按配置维度拉取报表并去重入库。"""
    base_url = settings.FLYMOBI_API_BASE_URL
    token = settings.FLYMOBI_API_TOKEN

    if not token or not token.strip():
        skip_msg = "跳过: FlyMobi API 未配置（请在 .env 设置 FLYMOBI_API_TOKEN）"
        logger.warning(skip_msg)
        set_task_result(FLYMOBI_API_TASK_NAME, skip_msg)
        return

    fm_start, fm_end = resolve_upstream_date_range(
        start_date, end_date, early_morning_dual_day=True,
    )
    notify_params = {"起始日期": fm_start, "终止日期": fm_end}

    enabled_reports = [r for r in _FLYMOBI_REPORTS if _is_report_enabled(r["env_flag"])]
    if not enabled_reports:
        skip_msg = "跳过: FlyMobi 未开启任何报表维度（FLYMOBI_API_FETCH_COUNTRY/UNIT/DAILY 均为 false）"
        logger.warning(skip_msg)
        set_task_result(FLYMOBI_API_TASK_NAME, skip_msg)
        return

    summaries: list[str] = []
    transient_errors: list[str] = []
    hard_errors: list[str] = []

    for report in enabled_reports:
        report_label = report["label"]
        try:
            async def _make_fetch(p=report["path"], lb=report_label):
                return await fetch_flymobi_rows(
                    base_url=base_url,
                    token=token,
                    start=fm_start,
                    end=fm_end,
                    path=p,
                    label=lb,
                )

            outcome = await run_upstream_import_task(
                FLYMOBI_API_TASK_NAME,
                credentials=None,
                fetch_data=_make_fetch,
                field_mapping=report["mapping"],
                source="FlyMobi定时任务",
                notify_title=f"FlyMobi ({report_label.split()[-1]})",
                data_transform=(
                    preprocess_flymobi_country_rows
                    if report["path"] == FLYMOBI_PATH_COUNTRY
                    else None
                ),
                data_source=DATA_SOURCE_FLYMOBI,
                log_label=report_label,
                notify_params=notify_params,
            )
            if outcome == UpstreamTaskOutcome.SUCCESS:
                summaries.append(f"{report_label}: 成功")
            elif outcome == UpstreamTaskOutcome.SKIPPED_TRANSIENT:
                transient_errors.append(f"{report_label}: 上游暂时不可达")
            else:
                # SKIPPED_CONFIG（本任务 credentials=None，正常不会到这里）
                transient_errors.append(f"{report_label}: 已跳过({outcome.value})")
        except Exception as exc:
            err = f"{report_label}: {exc}"
            hard_errors.append(err)
            # 不带 exc_info：汇总后若需失败再由调度器统一记录堆栈
            logger.error("FlyMobi 报表拉数失败 - %s", err)

    if hard_errors and not summaries and not transient_errors:
        msg = f"执行失败: {'; '.join(hard_errors)}"
        set_task_result(FLYMOBI_API_TASK_NAME, msg)
        raise RuntimeError(msg)

    if hard_errors:
        msg = (
            f"部分失败: {'; '.join(hard_errors)}"
            + (f" | 软跳过: {'; '.join(transient_errors)}" if transient_errors else "")
            + (f" | 成功: {'; '.join(summaries)}" if summaries else "")
        )
        set_task_result(FLYMOBI_API_TASK_NAME, msg)
        raise RuntimeError(msg)

    if transient_errors and not summaries:
        soft_msg = f"软跳过: 上游暂时不可达，等待下次调度 | {'; '.join(transient_errors)}"
        logger.warning("[%s] %s", FLYMOBI_API_TASK_NAME, soft_msg)
        log_scheduled_task_skip(
            FLYMOBI_API_TASK_NAME, "上游网络瞬时故障", detail="; ".join(transient_errors)
        )
        set_task_result(FLYMOBI_API_TASK_NAME, soft_msg)
        return

    if transient_errors and summaries:
        msg = (
            f"部分跳过(上游暂时不可达): {'; '.join(transient_errors)} "
            f"| 成功: {'; '.join(summaries)}"
        )
        logger.warning("[%s] %s", FLYMOBI_API_TASK_NAME, msg)
        set_task_result(FLYMOBI_API_TASK_NAME, msg)
        return

    set_task_result(FLYMOBI_API_TASK_NAME, "执行成功: " + "; ".join(summaries))
