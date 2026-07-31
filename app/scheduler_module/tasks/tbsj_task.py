"""
yangyangdeyi（TBSJ）上游广告数据拉取定时任务。
"""
import logging

from app.core.ad_data_metadata import DATA_SOURCE_TBSJ
from app.core.config import settings
from app.scheduler_module.task_names import TBSJ_API_TASK_NAME
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import fetch_tbsj_rows
from app.scheduler_module.upstream_http import post_form, post_json, UpstreamTransientError
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

logger = logging.getLogger(__name__)

# 默认 Base；可用 .env TBSJ_API_BASE_URL 覆盖（便于上游改路径时不发版改硬编码）
TBSJ_URL = (getattr(settings, "TBSJ_API_BASE_URL", None) or "https://data.tongbaishijia.com/api/thirdservice").rstrip("/")
TBSJ_HEADERS = {"Content-Type": "application/json;charset=utf-8"}

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


def _extract_access_token(token_json: dict) -> str:
    """兼容顶层或 data.access_token 两种响应结构。"""
    token = token_json.get("access_token") or ""
    if not token and isinstance(token_json.get("data"), dict):
        token = token_json["data"].get("access_token") or ""
    return str(token).strip()


async def _fetch_tbsj_token(username: str, password: str) -> str:
    """
    获取 TBSJ access_token。

    先 JSON body，若上游返回 404/鉴权类失败再尝试 form（旧联调脚本形态）。
    """
    token_url = f"{TBSJ_URL}/token"
    creds = {"username": username, "password": password}
    try:
        token_json = await post_json(
            token_url,
            json_body=creds,
            headers=TBSJ_HEADERS,
            label="TBSJ Token API",
            verify=False,
        )
    except UpstreamTransientError:
        # 瞬时网络故障直接上抛，由 run_upstream_import_task 软跳过
        raise
    except Exception as json_err:
        err_text = str(json_err)
        # 仅真正的 HTTP 404 才改走 form；避免响应体/其它错误文案误含 "404"
        if "状态码=404" not in err_text and "status=404" not in err_text:
            raise
        logger.warning(
            "TBSJ Token JSON 提交失败（%s），改用 form 重试 URL=%s",
            err_text[:160],
            token_url,
        )
        token_json = await post_form(
            token_url,
            form_body=creds,
            headers=None,
            label="TBSJ Token API(form)",
            verify=False,
        )

    access_token = _extract_access_token(token_json)
    if not access_token:
        raise Exception(f"TBSJ API 响应中缺少 access_token: {token_json}")
    return access_token


async def tbsj_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """yangyangdeyi 定时任务：Token 鉴权后拉数并入库。"""
    username = settings.TBSJ_API_USERNAME
    password = settings.TBSJ_API_PASSWORD
    tbsj_start, tbsj_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )
    notify_params = {"起始日期": tbsj_start, "终止日期": tbsj_end}

    async def fetch_data():
        access_token = await _fetch_tbsj_token(username, password)
        auth_headers = {**TBSJ_HEADERS, "Authorization": f"Bearer {access_token}"}
        return await fetch_tbsj_rows(
            base_url=TBSJ_URL,
            start=tbsj_start,
            end=tbsj_end,
            headers=auth_headers,
        )

    await run_upstream_import_task(
        TBSJ_API_TASK_NAME,
        credentials=(username, password),
        skip_hint="跳过: TBSJ API 未配置（请在 .env 设置 TBSJ_API_USERNAME / TBSJ_API_PASSWORD）",
        fetch_data=fetch_data,
        field_mapping=TBSJ_FIELD_MAPPING,
        source="yangyangdeyi定时任务",
        notify_title="yangyangdeyi",
        data_source=DATA_SOURCE_TBSJ,
        notify_params=notify_params,
    )
