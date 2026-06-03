"""
Pomiad 定时任务模块
功能：从 Pomiad API 获取广告明细数据，检查重复后插入到数据库
"""
import logging
from datetime import datetime

import pytz

from app.core.config import settings
from app.scheduler_module.task_names import POMIAD_API_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.task_utils import (
    resolve_upstream_date_range,
    upstream_credential_missing,
)
from app.scheduler_module.upstream_fetch import fetch_pomiad_rows
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)

POMIAD_FIELD_MAPPING = {
    "date": "data_date_f",
    "ad_unit": "ad_unit_name",
    "product_name": "domain_name",
    "country_code": "country_name",
    "request_count": "ad_request",
    "match_count": "match_count",
    "display_count": "imps",
    "click_count": "clicks",
    "revenue_before_deduct": "final_revenue",
    "ecpm_before_deduct": "cpm",
    "cpc": "cpc",
}


def preprocess_pomiad_rows(ad_data: list) -> list:
    """domain_name 为空时回退到 site"""
    for item in ad_data:
        if not str(item.get("domain_name") or "").strip():
            item["domain_name"] = (item.get("site") or "").strip()
    return ad_data


async def pomiad_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    username = settings.POMIAD_API_USERNAME
    password = settings.POMIAD_API_PASSWORD
    base_url = settings.POMIAD_API_BASE_URL

    if upstream_credential_missing(username, password):
        msg = "跳过: Pomiad API 未配置（请在 .env 设置 POMIAD_API_USERNAME / POMIAD_API_PASSWORD）"
        logger.warning(msg)
        set_task_result(POMIAD_API_TASK_NAME, msg)
        return

    current_time_str = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        f"{POMIAD_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）"
    )

    try:
        pomiad_start, pomiad_end = resolve_upstream_date_range(
            start_date,
            end_date,
            early_morning_dual_day=True,
        )
        data = await fetch_pomiad_rows(
            base_url=base_url,
            username=username,
            password=password,
            start=pomiad_start,
            end=pomiad_end,
            is_by_country=settings.POMIAD_IS_BY_COUNTRY,
            api_data_limit=settings.POMIAD_API_DATA_LIMIT,
        )
        await import_upstream_ad_data(
            task_name=POMIAD_API_TASK_NAME,
            data=data,
            field_mapping=POMIAD_FIELD_MAPPING,
            source="Pomiad定时任务",
            current_time_str=current_time_str,
            notify_title="Pomiad",
            data_transform=preprocess_pomiad_rows,
        )
    except Exception as e:
        error_msg = f"{POMIAD_API_TASK_NAME} 执行失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.warning(f"[Pomiad API获取数据] {error_msg}")
        raise
