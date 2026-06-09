"""
Skymobi 上游广告数据拉取定时任务。

功能说明：
- 从 Skymobi CRM API 拉取 H5 广告单元日报，映射字段后去重写入 ad_data
- 使用 fetch_skymobi_rows 封装鉴权与分页

在系统中的位置：
- 由 SKYMOBI_API_TASK_NAME 调度

注意事项：
1. Skymobi 时区与报表日期须与 resolve_upstream_date_range 一致
2. 新增单元类型时检查映射是否覆盖全部必填列
"""
import logging
from datetime import datetime, timedelta

import pytz

from app.core.config import settings
from app.scheduler_module.task_names import SKYMOBI_API_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.task_utils import upstream_credential_missing
from app.scheduler_module.upstream_fetch import fetch_skymobi_rows
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)

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
    """
    Skymobi 定时拉数：单日查询，凌晨 0-2 点默认拉昨日数据。

    Args:
        start_date: 指定日期则覆盖自动推算；end_date 参数保留兼容暂未使用
    """
    api_id = settings.SKYMOBI_API_ID
    api_key = settings.SKYMOBI_API_KEY

    current_time_str = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"{SKYMOBI_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")

    if upstream_credential_missing(api_id, api_key):
        msg = "跳过: Skymobi API 未配置（请在 .env 设置 SKYMOBI_API_ID / SKYMOBI_API_KEY）"
        logger.warning(msg)
        set_task_result(SKYMOBI_API_TASK_NAME, msg)
        return

    try:
        if start_date:
            date_str = start_date
        else:
            app_now = datetime.now(APP_TIMEZONE)
            today_str = app_now.strftime("%Y-%m-%d")
            if 0 <= app_now.hour <= 2:
                date_str = (app_now - timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                date_str = today_str

        data = await fetch_skymobi_rows(
            api_id=api_id,
            api_key=api_key,
            date_str=date_str,
        )
        await import_upstream_ad_data(
            task_name=SKYMOBI_API_TASK_NAME,
            data=data,
            field_mapping=SKYMOBI_FIELD_MAPPING,
            source="Skymobi定时任务",
            current_time_str=current_time_str,
            notify_title="Skymobi",
        )
    except Exception as e:
        error_msg = f"{SKYMOBI_API_TASK_NAME} 执行失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.warning(f"[Skymobi] {error_msg}")
        raise
