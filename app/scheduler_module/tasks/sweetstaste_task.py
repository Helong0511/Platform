"""
SweetStaste 上游广告数据拉取定时任务。

功能说明：
- 从 SweetStaste（alldata.onesefuns.top）GET /api/v1/get-ad-data 拉取广告单元明细
- 响应列为哈希键，经 display_names 还原后按 unit 维度入库
- 未配置 SWEETSTASTE_API_KEY 时跳过并写入说明

在系统中的位置：
- 由 SWEETSTASTE_API_TASK_NAME（「SweetStaste API获取数据」）调度

注意事项：
1. 不要传 summary_type=date_link（会把广告单元打成 0，变成日期+链接汇总）
2. data.total 是收益合计，分页以 last_page 为准
"""
from app.core.ad_data_metadata import DATA_SOURCE_SWEETSTASTE, REPORT_TYPE_UNIT
from app.core.config import settings
from app.scheduler_module.task_names import SWEETSTASTE_API_TASK_NAME
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import fetch_sweetstaste_rows
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

# 规范化后的稳定字段 → 平台 ad_data 字段（normalize 已写成同名）
SWEETSTASTE_FIELD_MAPPING = {
    "date": "date",
    "product_name": "product_name",
    "ad_unit": "ad_unit",
    "request_count": "request_count",
    "match_count": "match_count",
    "display_count": "display_count",
    "click_count": "click_count",
    "revenue_before_deduct": "revenue_before_deduct",
    "ecpm_before_deduct": "ecpm_before_deduct",
}


async def sweetstaste_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """SweetStaste 定时任务：分页拉取广告单元报表并入库。"""
    api_key = settings.SWEETSTASTE_API_KEY
    base_url = settings.SWEETSTASTE_API_BASE_URL
    site_name = settings.SWEETSTASTE_API_SITE_NAME
    ss_start, ss_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_params = {"起始日期": ss_start, "终止日期": ss_end}

    async def fetch_data():
        return await fetch_sweetstaste_rows(
            base_url=base_url,
            api_key=api_key,
            start_date=ss_start,
            end_date=ss_end,
            site_name=site_name,
        )

    await run_upstream_import_task(
        SWEETSTASTE_API_TASK_NAME,
        credentials=(api_key,),
        skip_hint="跳过: SweetStaste API 未配置（请在 .env 设置 SWEETSTASTE_API_KEY）",
        fetch_data=fetch_data,
        field_mapping=SWEETSTASTE_FIELD_MAPPING,
        source="SweetStaste定时任务",
        notify_title="SweetStaste",
        data_source=DATA_SOURCE_SWEETSTASTE,
        report_type=REPORT_TYPE_UNIT,
        log_label="SweetStaste API获取数据",
        notify_params=notify_params,
    )
