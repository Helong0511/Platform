"""
TQT 上游广告数据拉取定时任务。
"""
import logging

from app.core.config import settings
from app.scheduler_module.task_names import TQT_API_TASK_NAME
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import fetch_tqt_rows
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

logger = logging.getLogger(__name__)

TQT_URL = 'https://union.e-kivi.com/open/api/report/data'
TQT_HEADERS = {'Content-Type': 'application/json; charset=utf-8'}

TQT_FIELD_MAPPING = {
    "date": "date",
    "ad_unit": "ad_unit",
    "product_name": "url",
    "country_code": "country_code",
    "request_count": "requests",
    "match_count": "matche_que",
    "display_count": "adimpressions",
    "click_count": "clicks",
    "revenue_before_deduct": "estirevenue",
    "ecpm_before_deduct": "ecpm",
    "coverage_rate": "coverage",
    "display_rate": "display_rate",
    "click_rate": "ctr",
}


async def tqt_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """TQT 定时任务：按日期拉取广告明细并入库。"""
    tqt_app_key = settings.TQT_APP_KEY
    tqt_api_secret = settings.TQT_API_SECRET
    tqt_start, tqt_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_params = {"起始日期": tqt_start, "终止日期": tqt_end}

    async def fetch_data():
        tqt_params = {
            "appKey": tqt_app_key,
            "startDate": tqt_start,
            "endDate": tqt_end,
            "pageSize": 1000,
            "type": "country",
        }
        return await fetch_tqt_rows(
            url=TQT_URL,
            params=tqt_params,
            headers=TQT_HEADERS,
            api_secret=tqt_api_secret,
        )

    await run_upstream_import_task(
        TQT_API_TASK_NAME,
        credentials=(tqt_app_key, tqt_api_secret),
        skip_hint="跳过: TQT API 未配置（请在 .env 设置 TQT_APP_KEY / TQT_API_SECRET）",
        fetch_data=fetch_data,
        field_mapping=TQT_FIELD_MAPPING,
        source="TQT定时任务",
        notify_title="TQT",
        log_label="TQT获取广告数据",
        notify_params=notify_params,
    )
