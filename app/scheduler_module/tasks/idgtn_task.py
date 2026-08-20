"""
IDGTN Business Intelligence 上游广告数据拉取定时任务。

文档：tests/idgtn中国v1-4.pdf v1.9
- 接口3 /download/country：广告单元 + 日期 + 国家（具体国家+广告单元 → 平台 cross 维度）
- 鉴权：header apiKey + apiSecret
- 单日接口（reportDate=yyyy-MM-dd），无分页；任务内按日期范围循环累积后一次入库

字段说明（IDGTN 返回 → 平台 ad_data 字段）：
- adExchangeTotalRequests → request_count（请求数）
- matchRequests            → match_count（实际请求数）
- adExchangeLineItemLevelImpressions → display_count（曝光数 → 展示数）
- adExchangeLineItemLevelClicks       → click_count（点击数）
- adExchangeLineItemLevelRevenue      → revenue_before_deduct（收益，美元）
- adExchangeLineItemLevelAverageEcpm  → ecpm_before_deduct（千次曝光价，美元）
- adExchangeLineItemLevelCtr           → click_rate（预估转化率 → 点击率）
- adExchangeActiveViewViewableImpressionsRate → viewability_rate（可见度广告曝光率）
- pv                                   → pageviews（浏览量）
- domain                               → product_name（产品名匹配键，同 ZhiSuo 用 domain_name）
- adUnitName                           → ad_unit（广告单元名）
- countryCode                          → country_code（ISO-2 国家代码）
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from app.core.ad_data_metadata import (
    DATA_SOURCE_IDGTN,
    REPORT_TYPE_CROSS,
)
from app.core.config import settings
from app.scheduler_module.task_names import IDGTN_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    get_current_time_str,
    log_scheduled_task_skip,
    log_task_start,
    resolve_upstream_date_range,
    truncate_task_error_message,
)
from app.scheduler_module.upstream_fetch import fetch_idgtn_rows
from app.scheduler_module.upstream_http import UpstreamTransientError
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

# IDGTN /download/country 字段映射（具体国家+广告单元 → cross 维度）
IDGTN_COUNTRY_FIELD_MAPPING: dict[str, str] = {
    "date": "date",
    "product_name": "domain",
    "ad_unit": "adUnitName",
    "country_code": "countryCode",
    "request_count": "adExchangeTotalRequests",
    "match_count": "matchRequests",
    "display_count": "adExchangeLineItemLevelImpressions",
    "click_count": "adExchangeLineItemLevelClicks",
    "revenue_before_deduct": "adExchangeLineItemLevelRevenue",
    "ecpm_before_deduct": "adExchangeLineItemLevelAverageEcpm",
    "click_rate": "adExchangeLineItemLevelCtr",
    "viewability_rate": "adExchangeActiveViewViewableImpressionsRate",
    "pageviews": "pv",
}


def _iter_dates(start: str, end: str):
    """按天迭代 [start, end] 闭区间，每天产出 yyyy-MM-dd。"""
    start_d = datetime.strptime(start, "%Y-%m-%d").date()
    end_d = datetime.strptime(end, "%Y-%m-%d").date()
    if end_d < start_d:
        start_d, end_d = end_d, start_d
    cur = start_d
    while cur <= end_d:
        yield cur.isoformat()
        cur += timedelta(days=1)


async def idgtn_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """IDGTN 定时拉数：按日期范围循环调用 /download/country，累积后一次入库。"""
    base_url = settings.IDGTN_API_BASE_URL
    api_key = settings.IDGTN_API_KEY
    api_secret = settings.IDGTN_API_SECRET
    fetch_country = settings.IDGTN_API_FETCH_COUNTRY

    if not api_key.strip() or not api_secret.strip():
        msg = "跳过: IDGTN API 未配置（请在 .env 设置 IDGTN_API_KEY / IDGTN_API_SECRET）"
        logger.warning(msg)
        set_task_result(IDGTN_API_TASK_NAME, msg)
        return

    if not fetch_country:
        msg = "跳过: IDGTN 未启用 country 维度（IDGTN_API_FETCH_COUNTRY=false）"
        logger.warning(msg)
        set_task_result(IDGTN_API_TASK_NAME, msg)
        return

    idgtn_start, idgtn_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_params = {"起始日期": idgtn_start, "终止日期": idgtn_end}
    current_time_str = get_current_time_str()
    log_task_start(IDGTN_API_TASK_NAME)

    # ---------- 按天循环拉数累积 ----------
    all_rows: list[Any] = []
    fetched_days: list[str] = []
    empty_days: list[str] = []
    transient_errors: list[str] = []
    hard_errors: list[str] = []

    for day in _iter_dates(idgtn_start, idgtn_end):
        try:
            result = await fetch_idgtn_rows(
                base_url=base_url,
                api_key=api_key,
                api_secret=api_secret,
                report_date=day,
                label="IDGTN /download/country",
            )
            rows = list(result.rows)
            logger.info("IDGTN country 拉取 %s: %d 条", day, len(rows))
            if rows:
                all_rows.extend(rows)
                fetched_days.append(f"{day}({len(rows)})")
            else:
                empty_days.append(day)
        except UpstreamTransientError as e:
            transient_errors.append(f"{day}: {truncate_task_error_message(str(e))}")
            logger.warning("IDGTN country %s 上游瞬时故障: %s", day, e)
        except Exception as e:
            detail = truncate_task_error_message(str(e))
            hard_errors.append(f"{day}: {detail}")
            logger.error("IDGTN country %s 拉取失败: %s", day, detail)

    # ---------- 入库 ----------
    # 单日或单段硬错误且无任何成功数据：按整体失败抛出
    if not all_rows and hard_errors and not transient_errors:
        msg = f"执行失败: {'; '.join(hard_errors)}"
        logger.error("[%s] %s", IDGTN_API_TASK_NAME, msg)
        set_task_result(IDGTN_API_TASK_NAME, msg)
        raise RuntimeError(msg)

    if not all_rows and transient_errors and not hard_errors:
        soft_msg = (
            f"软跳过: 上游暂时不可达，等待下次调度 | {'; '.join(transient_errors)}"
        )
        logger.warning("[%s] %s", IDGTN_API_TASK_NAME, soft_msg)
        log_scheduled_task_skip(
            IDGTN_API_TASK_NAME, "上游网络瞬时故障", detail="; ".join(transient_errors)
        )
        set_task_result(IDGTN_API_TASK_NAME, soft_msg)
        return

    summary = await import_upstream_ad_data(
        task_name=IDGTN_API_TASK_NAME,
        data=all_rows,
        field_mapping=IDGTN_COUNTRY_FIELD_MAPPING,
        source="IDGTN定时任务-国家+广告单元",
        current_time_str=current_time_str,
        notify_title="IDGTN",
        data_source=DATA_SOURCE_IDGTN,
        report_type=REPORT_TYPE_CROSS,
        upstream_account="",
        notify_params=notify_params,
    )

    # ---------- 汇总结果 ----------
    fetch_block = ""
    if fetched_days:
        fetch_block = f" | 拉取: {len(fetched_days)} 天 {len(all_rows)} 行"
    if empty_days:
        fetch_block += f" | 空数据: {len(empty_days)} 天"
    if transient_errors:
        fetch_block += f" | 软跳过: {len(transient_errors)} 天"
    if hard_errors:
        fetch_block += f" | 失败: {len(hard_errors)} 天"

    if hard_errors and all_rows:
        # 部分成功 + 部分硬错误
        msg = f"部分成功: {summary}{fetch_block}"
        logger.warning("[%s] %s", IDGTN_API_TASK_NAME, msg)
        set_task_result(IDGTN_API_TASK_NAME, msg)
        return

    if transient_errors and all_rows:
        msg = f"部分成功(上游瞬时故障已跳过): {summary}{fetch_block}"
        logger.warning("[%s] %s", IDGTN_API_TASK_NAME, msg)
        set_task_result(IDGTN_API_TASK_NAME, msg)
        return

    set_task_result(IDGTN_API_TASK_NAME, f"执行成功: {summary}{fetch_block}")
