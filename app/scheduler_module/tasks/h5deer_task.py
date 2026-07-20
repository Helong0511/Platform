"""
H5 Deer 上游广告数据拉取定时任务。

功能说明：
- 从 H5 Deer 开放 API（user_oauth/token + v1/api/h5report）拉取广告明细并入库
- 未配置 H5DEER_API_USERNAME/PASSWORD 时跳过并写入说明

在系统中的位置：
- 由 H5DEER_API_TASK_NAME（「H5 Deer API获取数据」）调度

注意事项：
1. Authorization 头为 ``JWT <token>``，与 Bearer 不同
2. 默认最细颗粒度 date,url,country_code,ad_nuit（国家+广告单元交叉）
3. 上游广告单元字段拼写为 ad_nuit（文档原文），映射到平台 ad_unit
"""
from app.core.ad_data_metadata import DATA_SOURCE_H5DEER
from app.core.config import settings
from app.scheduler_module.task_names import H5DEER_API_TASK_NAME
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import fetch_h5deer_rows
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

# H5 Deer h5report → 平台标准字段（参见对接文档 Response data 字段）
H5DEER_FIELD_MAPPING = {
    "date": "date",
    "product_name": "url",
    "ad_unit": "adNuit",
    "country_code": "countryCode",
    "request_count": "adRequests",
    "match_count": "adMatchRequests",
    "display_count": "adImpressions",
    "click_count": "clicks",
    "revenue_before_deduct": "estimatedRevenue",
    "ecpm_before_deduct": "ecpm",
    "coverage_rate": "coverRate",
    "display_rate": "impressionsRate",
    "click_rate": "ctr",
}


async def h5deer_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """H5 Deer 定时任务：登录鉴权后分页拉取报表并入库。"""
    username = settings.H5DEER_API_USERNAME
    password = settings.H5DEER_API_PASSWORD
    base_url = settings.H5DEER_API_BASE_URL
    h5deer_start, h5deer_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_params = {"起始日期": h5deer_start, "终止日期": h5deer_end}

    async def fetch_data():
        return await fetch_h5deer_rows(
            base_url=base_url,
            username=username,
            password=password,
            start=h5deer_start,
            end=h5deer_end,
            dimension=settings.H5DEER_API_DIMENSION,
            limit=settings.H5DEER_API_LIMIT,
        )

    await run_upstream_import_task(
        H5DEER_API_TASK_NAME,
        credentials=(username, password),
        skip_hint="跳过: H5 Deer API 未配置（请在 .env 设置 H5DEER_API_USERNAME / H5DEER_API_PASSWORD）",
        fetch_data=fetch_data,
        field_mapping=H5DEER_FIELD_MAPPING,
        source="H5 Deer定时任务",
        notify_title="H5 Deer",
        data_source=DATA_SOURCE_H5DEER,
        log_label="H5 Deer API获取数据",
        notify_params=notify_params,
    )
