"""
zhisuo 上游广告数据拉取定时任务。

功能说明：
- 从 zhisuo API 获取广告单元数据，检查重复后插入 ad_data
- 支持多账号顺序拉取后合并入库
"""
import logging

from app.core.config import settings
from app.scheduler_module.task_names import ZHISUO_API_TASK_NAME
from app.scheduler_module.task_result_store import set_task_result
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import fetch_zhisuo_unit_rows
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

logger = logging.getLogger(__name__)

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
    """zhisuo 定时拉数：多账号拉取合并后入库。"""
    accounts = settings.get_zhisuo_accounts()
    base_url = settings.ZHISUO_API_BASE_URL

    if not accounts:
        msg = (
            "跳过: Zhisuo API 未配置（请在 .env 设置 ZHISUO_API_CLIENT_ID / ZHISUO_API_KEY，"
            "或 ZHISUO_API_CLIENT_ID_2~4 / ZHISUO_API_KEY_2~4，或 ZHISUO_API_ACCOUNTS）"
        )
        logger.warning(msg)
        set_task_result(ZHISUO_API_TASK_NAME, msg)
        return

    zhisuo_start, zhisuo_end = resolve_upstream_date_range(
        start_date,
        end_date,
        early_morning_dual_day=True,
    )

    async def fetch_data():
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
        return all_data

    await run_upstream_import_task(
        ZHISUO_API_TASK_NAME,
        fetch_data=fetch_data,
        field_mapping=ZHISUO_FIELD_MAPPING,
        source="zhisuo定时任务",
        notify_title="zhisuo",
    )
