"""
Huguang 上游广告数据拉取定时任务。

功能说明：
- 从 Huguang API 获取广告明细，经字段映射与去重写入 ad_data 表
- 日期区间由 resolve_upstream_date_range 统一解析

在系统中的位置：
- 由 HUGUANG_API_TASK_NAME 调度

注意事项：
1. 与其它上游任务共用 upstream_import，勿重复实现提交/通知逻辑
2. 失败摘要写入 set_task_result 供管理端展示
"""
import logging
from datetime import datetime

import pytz

from app.core.config import settings
from app.scheduler_module.task_names import HUGUANG_API_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.task_utils import (
    resolve_upstream_date_range,
    upstream_credential_missing,
)
from app.scheduler_module.upstream_fetch import fetch_huguang_rows
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)

# 上游字段 → 平台 ad_data 标准字段
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
    """
    Huguang 定时拉数任务：拉取国家维度报表并去重入库。

    Args:
        start_date: 可选起始日期 YYYY-MM-DD，缺省由 resolve_upstream_date_range 推算
        end_date: 可选结束日期；凌晨 0-2 点可能拉取昨日+今日双日数据
    """
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
