"""
Huguang定时任务模块
功能：从Huguang API获取广告数据，检查重复后插入到数据库
"""
import logging
from datetime import datetime

import pytz

from app.core.config import settings
from app.scheduler_module.task_names import HUGUANG_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import (
    resolve_upstream_date_range,
    upstream_credential_missing,
)
from app.scheduler_module.upstream_fetch import fetch_huguang_rows
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)

HUGUANG_FIELD_MAPPING = {
    "date": "date",
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
    api_key = settings.HUGUANG_API_KEY
    domain = settings.HUGUANG_API_DOMAIN
    username = settings.HUGUANG_API_USERNAME

    if upstream_credential_missing(api_key, domain, username):
        msg = "跳过: Huguang API 未配置（请在 .env 设置 HUGUANG_API_KEY / DOMAIN / USERNAME）"
        logger.warning(msg)
        set_task_result(HUGUANG_API_TASK_NAME, msg)
        return

    current_time_str = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"{HUGUANG_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")

    try:
        huguang_start, huguang_end = resolve_upstream_date_range(
            start_date,
            end_date,
            early_morning_dual_day=True,
        )
        data = await fetch_huguang_rows(
            domain=domain,
            api_key=api_key,
            username=username,
            start=huguang_start,
            end=huguang_end,
        )
        await import_upstream_ad_data(
            task_name=HUGUANG_API_TASK_NAME,
            data=data,
            field_mapping=HUGUANG_FIELD_MAPPING,
            source="Huguang定时任务",
            current_time_str=current_time_str,
            notify_title="Huguang",
        )
    except Exception as e:
        error_msg = f"{HUGUANG_API_TASK_NAME} 执行失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.warning(f"[Huguang API获取数据] {error_msg}")
        raise
