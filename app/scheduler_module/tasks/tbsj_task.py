"""
yangyangdeyi定时任务模块
功能：从yangyangdeyi API获取广告数据，检查重复后插入到数据库
"""
import logging
from datetime import datetime, timedelta

import pytz

from app.core.config import settings
from app.scheduler_module.upstream_fetch import fetch_tbsj_rows
from app.scheduler_module.upstream_import import import_upstream_ad_data
from app.scheduler_module.upstream_http import post_json
from app.scheduler_module.task_names import TBSJ_API_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.task_utils import upstream_credential_missing

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)


# 应用时区配置（从统一配置读取）
# 用于将本地时间转换为标准时区
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)


async def tbsj_api_task(
        start_date: str | None = None,
        end_date: str | None = None
) -> None:
    """
    yangyangdeyi定时任务主函数
    
    参数:
        start_date: 可选，起始日期 (格式: YYYY-MM-DD)，如果不提供则根据时间自动选择
        end_date: 可选，结束日期 (格式: YYYY-MM-DD)，如果不提供则使用start_date
    """
    # ========== yangyangdeyi API配置 ==========
    # HTTP请求头配置
    Headers = {'Content-Type': 'application/json;charset=utf-8'}

    # API请求地址
    tbsj_url = 'https://data.tongbaishijia.com/api/thirdservice'

    username = settings.TBSJ_API_USERNAME
    password = settings.TBSJ_API_PASSWORD

    if upstream_credential_missing(username, password):
        msg = "跳过: TBSJ API 未配置（请在 .env 设置 TBSJ_API_USERNAME / TBSJ_API_PASSWORD）"
        logger.warning(msg)
        set_task_result(TBSJ_API_TASK_NAME, msg)
        return

    app_time = datetime.now(APP_TIMEZONE)
    current_time_str = app_time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"{TBSJ_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")

    try:
        # ============================================
        # 任务主逻辑开始
        # ============================================

        token_post = {
            "username": username,
            "password": password
        }

        token_json = await post_json(
            tbsj_url + "/token",
            json_body=token_post,
            headers=Headers,
            label="TBSJ Token API",
            verify=False,
        )
        access_token = token_json.get("access_token", "")
        if not access_token:
            raise Exception("TBSJ API 响应中缺少 access_token")
        Headers["Authorization"] = f"Bearer {access_token}"

        # 修改日期计算逻辑
        if start_date:
            # 使用传入的日期
            if end_date:
                tbsj_start = start_date
                tbsj_end = end_date
            else:
                tbsj_start = start_date
                tbsj_end = start_date
        else:
            # 原有的自动计算逻辑
            app_now = datetime.now(APP_TIMEZONE)
            app_yesterday = app_now - timedelta(days=1)
            yesterday_str = app_yesterday.strftime("%Y-%m-%d")
            today_str = app_now.strftime("%Y-%m-%d")

            if 0 <= app_now.hour <= 2:
                tbsj_start = yesterday_str
                tbsj_end = today_str
            else:
                tbsj_start = today_str
                tbsj_end = today_str

        tbsj_params = {
            "page": 1,
            "limit": 1000,
            "start": tbsj_start,
            "end": tbsj_end
        }

        data = await fetch_tbsj_rows(
            base_url=tbsj_url,
            params=tbsj_params,
            headers=Headers,
        )
        await import_upstream_ad_data(
            task_name=TBSJ_API_TASK_NAME,
            data=data,
            field_mapping={
                "date": "date",
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
            },
            source="yangyangdeyi定时任务",
            current_time_str=current_time_str,
            notify_title="yangyangdeyi",
        )

    except Exception as e:
        # ========== 全局错误处理 ==========

        # 捕获任务执行过程中的任何异常
        # 注意：如果任务执行失败，异常会被捕获并记录
        # 定时任务调度器的锁机制会自动释放，错误信息会保存到数据库

        error_msg = f"{TBSJ_API_TASK_NAME} 执行失败: {str(e)}"
        # 记录详细错误信息（包括完整的堆栈跟踪）
        # 注意：只记录一次，避免重复。如果业务层已记录错误，这里只记录简要信息
        logger.error(error_msg, exc_info=True)

        # 重新抛出异常，让定时任务调度器的锁机制能够记录错误状态
        # 这样可以在数据库中标记任务执行失败，便于后续排查问题
        raise
