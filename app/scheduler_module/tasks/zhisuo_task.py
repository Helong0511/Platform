"""
zhisuo 上游广告数据拉取定时任务。

功能说明：
- 从 zhisuo API 获取广告单元数据，检查重复后插入 ad_data
- 通过 fetch_zhisuo_unit_rows 请求 /api/channelunit 接口

在系统中的位置：
- 由 ZHISUO_API_TASK_NAME 调度

注意事项：
1. 签名/鉴权参数变更须同步 upstream_fetch
2. 空响应与业务错误码区分处理，避免误记为成功
"""
import logging
from datetime import datetime, timedelta

import pytz

from app.core.config import settings
from app.scheduler_module.task_names import ZHISUO_API_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.upstream_fetch import fetch_zhisuo_unit_rows
from app.scheduler_module.upstream_import import import_upstream_ad_data

logger = logging.getLogger(__name__)

APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)

ZHISUO_FIELD_MAPPING = {
    "date": "date",
    "ad_unit": "ad_unit_name",
    "product_name": "domain_name",
    "request_count": "ad_requests",
    "match_count": "matched_requests",
    "display_count": "ad_impressions",
    "click_count": "clicks",
    "revenue_before_deduct": "estimated_earnings",
    "ecpm_before_deduct": "ecpm",
    "coverage_rate": "coverage_rate",
    "display_rate": "display_rate",
    "click_rate": "click_through_rate",
    "cpc": "cpc",
}


async def zhisuo_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """
    zhisuo 定时拉数：支持多账号顺序拉取后合并入库。

    单账号失败不阻断其余账号；仅当全部失败时抛异常。凌晨 0-2 点拉昨日至今日。
    """
    accounts = settings.get_zhisuo_accounts()
    base_url = settings.ZHISUO_API_BASE_URL

    if not accounts:
        msg = (
            "跳过: Zhisuo API 未配置（请在 .env 设置 ZHISUO_API_CLIENT_ID / ZHISUO_API_KEY，"
            "或 ZHISUO_API_CLIENT_ID_2 / ZHISUO_API_KEY_2，或 ZHISUO_API_ACCOUNTS）"
        )
        logger.warning(msg)
        set_task_result(ZHISUO_API_TASK_NAME, msg)
        return

    app_time = datetime.now(APP_TIMEZONE)
    current_time_str = app_time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        f"{ZHISUO_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）"
    )

    try:
        if start_date:
            if end_date:
                zhisuo_start = start_date
                zhisuo_end = end_date
            else:
                zhisuo_start = start_date
                zhisuo_end = start_date
        else:
            app_now = datetime.now(APP_TIMEZONE)
            app_yesterday = app_now - timedelta(days=1)
            yesterday_str = app_yesterday.strftime("%Y-%m-%d")
            today_str = app_now.strftime("%Y-%m-%d")

            if 0 <= app_now.hour <= 2:
                zhisuo_start = yesterday_str
                zhisuo_end = today_str
            else:
                zhisuo_start = today_str
                zhisuo_end = today_str

        all_data = []
        fetch_errors: list[str] = []
        for acc in accounts:
            client_id = acc["client_id"]
            try:
                rows = await fetch_zhisuo_unit_rows(
                    base_url=base_url,
                    client_id=client_id,
                    api_key=acc["api_key"],
                    start=zhisuo_start,
                    end=zhisuo_end,
                )
                all_data.extend(rows)
                logger.info("Zhisuo 账号 %s 拉取 %d 条", client_id, len(rows))
            except Exception as e:
                err_msg = f"账号 {client_id}: {e}"
                fetch_errors.append(err_msg)
                logger.error("Zhisuo 拉取失败 - %s", err_msg, exc_info=True)

        if fetch_errors and not all_data:
            raise Exception("所有 Zhisuo 账号拉取失败: " + "; ".join(fetch_errors))
        if fetch_errors:
            logger.warning("部分 Zhisuo 账号拉取失败: %s", "; ".join(fetch_errors))

        await import_upstream_ad_data(
            task_name=ZHISUO_API_TASK_NAME,
            data=all_data,
            field_mapping=ZHISUO_FIELD_MAPPING,
            source="zhisuo定时任务",
            current_time_str=current_time_str,
            notify_title="zhisuo",
        )

    except Exception as e:
        error_msg = f"{ZHISUO_API_TASK_NAME} 执行失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise
