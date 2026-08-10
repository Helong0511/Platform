"""
Addermobi 上游广告数据拉取定时任务。
"""
import json
import logging

from app.core.ad_data_metadata import DATA_SOURCE_ADDERMOBI
from app.core.config import settings
from app.scheduler_module.task_names import ADDERMOBI_API_TASK_NAME
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import fetch_addermobi_rows
from app.scheduler_module.upstream_http import post_json
from app.scheduler_module.upstream_import import preprocess_addermobi_match_counts
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

logger = logging.getLogger(__name__)

ADDERMOBI_FIELD_MAPPING = {
    "date": "Revenue_time",
    "ad_unit": "ad_unit",
    "product_name": "link",
    "country_code": "Country_Code",
    "request_count": "AdRequests",
    "match_count": "MatchedAdRequests",
    "display_count": "Impressions",
    "click_count": "Clicks",
    "viewability_rate": "ActiveViewViewability",
    "cpc": "CPC",
    "ecpm_before_deduct": "eCPM",
    "coverage_rate": "AdRequestsCoverage",
    "display_rate": "ad_impression_rate",
    "click_rate": "CTR",
    "revenue_before_deduct": "EstimatedEarnings",
}


async def addermobi_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Addermobi 定时任务：登录鉴权后拉取报表并入库。"""
    username = settings.ADDERMOBI_API_USERNAME
    password = settings.ADDERMOBI_API_PASSWORD
    headers = {'Content-Type': 'application/json'}
    start_date_str, end_date_str = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_params = {"起始日期": start_date_str, "终止日期": end_date_str}

    async def fetch_data():
        login_json = await post_json(
            "https://api.addermobi.com/api/User/loginApi",
            json_body={"userName": username, "password": password},
            headers=headers,
            label="Addermobi Login API",
        )
        access_token = None
        if "data" in login_json and isinstance(login_json["data"], dict):
            access_token = login_json["data"].get("token") or login_json["data"].get(
                "access_token"
            )
        else:
            access_token = login_json.get("token") or login_json.get("access_token")
        if not access_token:
            raise Exception("Addermobi API 响应中缺少 access_token")

        auth_headers = {**headers, "Authorization": f"Bearer {access_token}"}
        wheres = [
            {"name": "Revenue_time", "value": start_date_str, "displayType": "thanorequal"},
            {"name": "Revenue_time", "value": end_date_str, "displayType": "lessorequal"},
        ]
        payload = {
            "page": 1,
            "rows": 1000,
            "sort": "Revenue_time,Product_id",
            "order": "desc",
            "wheres": json.dumps(wheres),
        }
        return await fetch_addermobi_rows(
            url="https://api.addermobi.com/api/Revenue_DetailReports/GetData",
            payload=payload,
            headers=auth_headers,
        )

    await run_upstream_import_task(
        ADDERMOBI_API_TASK_NAME,
        credentials=(username, password),
        skip_hint="跳过: Addermobi API 未配置（请在 .env 设置 ADDERMOBI_API_USERNAME / PASSWORD）",
        fetch_data=fetch_data,
        field_mapping=ADDERMOBI_FIELD_MAPPING,
        source="Addermobi定时任务",
        notify_title="Addermobi",
        data_source=DATA_SOURCE_ADDERMOBI,
        data_transform=preprocess_addermobi_match_counts,
        log_label="Addermobi API获取数据",
        notify_params=notify_params,
    )
