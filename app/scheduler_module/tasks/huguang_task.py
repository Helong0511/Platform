"""
Huguang 上游广告数据拉取定时任务。

功能说明：
- 从 Huguang API 获取广告明细，经字段映射与去重写入 ad_data 表
- 日期区间由 resolve_upstream_date_range 统一解析

在系统中的位置：
- 由 HUGUANG_API_TASK_NAME 调度
"""
from app.core.config import settings
from app.scheduler_module.task_names import HUGUANG_API_TASK_NAME
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import fetch_huguang_rows
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

HUGUANG_FIELD_MAPPING = {
    "date": "date",
    "ad_unit": "ad_unit",
    "product_name": "url",
    "country_code": "country",
    "request_count": "request",
    "match_count": "match_req",
    "display_count": "show",
    "click_count": "click",
    "ecpm_before_deduct": "ecpm",
    "revenue_before_deduct": "channel_revenue",
}


async def huguang_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Huguang 定时拉数任务：拉取国家维度报表并去重入库。"""
    api_key = settings.HUGUANG_API_KEY
    domain = settings.HUGUANG_API_DOMAIN
    username = settings.HUGUANG_API_USERNAME
    huguang_start, huguang_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_params = {"起始日期": huguang_start, "终止日期": huguang_end}

    async def fetch_data():
        return await fetch_huguang_rows(
            domain=domain,
            api_key=api_key,
            username=username,
            start=huguang_start,
            end=huguang_end,
        )

    await run_upstream_import_task(
        HUGUANG_API_TASK_NAME,
        credentials=(api_key, domain, username),
        skip_hint="跳过: Huguang API 未配置（请在 .env 设置 HUGUANG_API_KEY / DOMAIN / USERNAME）",
        fetch_data=fetch_data,
        field_mapping=HUGUANG_FIELD_MAPPING,
        source="Huguang定时任务",
        notify_title="Huguang",
        log_label="Huguang API获取数据",
        notify_params=notify_params,
    )
