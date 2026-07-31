"""
Skymobi 上游广告数据拉取定时任务。

功能说明：
- 从 Skymobi CRM API 拉取 H5 广告单元日报，映射字段后去重写入 ad_data

在系统中的位置：
- 由 SKYMOBI_API_TASK_NAME 调度
"""
from datetime import datetime, timedelta

from app.core.ad_data_metadata import DATA_SOURCE_SKYMOBI
from app.core.config import settings
from app.scheduler_module.task_names import SKYMOBI_API_TASK_NAME
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import (
    UpstreamFetchResult,
    UpstreamFetchStats,
    fetch_skymobi_rows,
)
from app.scheduler_module.upstream_http import UpstreamTransientError
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

SKYMOBI_FIELD_MAPPING = {
    "date": "dt",
    "ad_unit": "ad_unit",
    "product_name": "link",
    "country_code": "country",
    "request_count": "req",
    "match_count": "req_ef",
    "display_count": "imp",
    "click_count": "click",
    "revenue_before_deduct": "income",
    "ecpm_before_deduct": "ecpm",
    "coverage_rate": "coverage_rate",
    "display_rate": "display_rate",
    "click_rate": "click_rate",
}


async def skymobi_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Skymobi 定时拉数：按日期区间逐日查询（默认昨日~今日）。"""
    api_id = settings.SKYMOBI_API_ID
    api_key = settings.SKYMOBI_API_KEY
    range_start, range_end = resolve_upstream_date_range(start_date, end_date)
    notify_params = {"起始日期": range_start, "终止日期": range_end}

    async def fetch_data():
        current = datetime.strptime(range_start, "%Y-%m-%d").date()
        end = datetime.strptime(range_end, "%Y-%m-%d").date()
        all_rows = []
        stats_list: list[UpstreamFetchStats] = []
        while current <= end:
            try:
                result = await fetch_skymobi_rows(
                    api_id=api_id,
                    api_key=api_key,
                    date_str=current.strftime("%Y-%m-%d"),
                )
            except UpstreamTransientError:
                # 已拉到的日期仍入库；若一天都没有则上抛由 runner 软跳过
                if all_rows:
                    break
                raise
            all_rows.extend(result.rows)
            stats_list.append(result.stats)
            current += timedelta(days=1)
        return UpstreamFetchResult(
            rows=all_rows,
            stats=UpstreamFetchStats.merge(*stats_list) if stats_list else UpstreamFetchStats(),
        )

    await run_upstream_import_task(
        SKYMOBI_API_TASK_NAME,
        credentials=(api_id, api_key),
        skip_hint="跳过: Skymobi API 未配置（请在 .env 设置 SKYMOBI_API_ID / SKYMOBI_API_KEY）",
        fetch_data=fetch_data,
        field_mapping=SKYMOBI_FIELD_MAPPING,
        source="Skymobi定时任务",
        notify_title="Skymobi",
        data_source=DATA_SOURCE_SKYMOBI,
        log_label="Skymobi",
        notify_params=notify_params,
    )
