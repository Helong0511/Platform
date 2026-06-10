"""
yangyangdeyi（TBSJ）上游广告数据拉取定时任务。
"""
import logging

from app.core.config import settings
from app.scheduler_module.task_names import TBSJ_API_TASK_NAME
from app.scheduler_module.task_utils import log_task_error, resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import fetch_tbsj_rows
from app.scheduler_module.upstream_http import post_json
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

logger = logging.getLogger(__name__)

TBSJ_URL = 'https://data.tongbaishijia.com/api/thirdservice'
TBSJ_HEADERS = {'Content-Type': 'application/json;charset=utf-8'}

TBSJ_FIELD_MAPPING = {
    "date": "date",
    "ad_unit": "ad_unit",
    "product_name": "product",
    "country_code": "country_code",
    "request_count": "ad_requests",
    "match_count": "ad_matches",
    "display_count": "ad_impressions",
    "click_count": "ad_clicks",
    "ecpm_before_deduct": "ecpm",
    "coverage_rate": "ad_coverage",
    "display_rate": "ad_impression_rate",
    "click_rate": "ctr",
    "revenue_before_deduct": "earnings",
}


async def tbsj_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """yangyangdeyi 定时任务：Token 鉴权后拉数并入库。"""
    username = settings.TBSJ_API_USERNAME
    password = settings.TBSJ_API_PASSWORD

    async def fetch_data():
        token_json = await post_json(
            TBSJ_URL + "/token",
            json_body={"username": username, "password": password},
            headers=TBSJ_HEADERS,
            label="TBSJ Token API",
            verify=False,
        )
        access_token = token_json.get("access_token", "")
        if not access_token:
            raise Exception("TBSJ API 响应中缺少 access_token")

        auth_headers = {**TBSJ_HEADERS, "Authorization": f"Bearer {access_token}"}
        tbsj_start, tbsj_end = resolve_upstream_date_range(
            start_date,
            end_date,
            early_morning_dual_day=True,
        )
        return await fetch_tbsj_rows(
            base_url=TBSJ_URL,
            params={"page": 1, "limit": 1000, "start": tbsj_start, "end": tbsj_end},
            headers=auth_headers,
        )

    try:
        await run_upstream_import_task(
            TBSJ_API_TASK_NAME,
            credentials=(username, password),
            skip_hint="跳过: TBSJ API 未配置（请在 .env 设置 TBSJ_API_USERNAME / TBSJ_API_PASSWORD）",
            fetch_data=fetch_data,
            field_mapping=TBSJ_FIELD_MAPPING,
            source="yangyangdeyi定时任务",
            notify_title="yangyangdeyi",
        )
    except Exception as e:
        log_timeout = "请求超时" in str(e) or "请求失败" in str(e)
        log_task_error(TBSJ_API_TASK_NAME, str(e), exc_info=not log_timeout)
        raise
