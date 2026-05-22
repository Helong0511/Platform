"""
Addermobi定时任务模块
功能：从Addermobi API获取广告数据，检查重复后插入到数据库
"""
import json
import logging
from datetime import datetime, timedelta

import pytz

from app.core.config import settings
from app.scheduler_module.task_names import ADDERMOBI_API_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.upstream_fetch import fetch_addermobi_rows
from app.scheduler_module.upstream_http import post_json
from app.scheduler_module.upstream_import import (
    import_upstream_ad_data,
    preprocess_addermobi_match_counts,
)
from app.scheduler_module.task_utils import upstream_credential_missing

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)


# 应用时区配置（从统一配置读取）
# 用于将本地时间转换为标准时区
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)


async def addermobi_api_task(
        start_date: str | None = None,
        end_date: str | None = None
) -> None:
    """
    Addermobi定时任务主函数
    
    参数:
        start_date: 可选，起始日期 (格式: YYYY-MM-DD)，如果不提供则根据时间自动选择
        end_date: 可选，结束日期 (格式: YYYY-MM-DD)，如果不提供则使用start_date
    """
    # ========== Addermobi API配置 ==========
    # HTTP请求头配置
    Headers = {'Content-Type': 'application/json'}

    username = settings.ADDERMOBI_API_USERNAME
    password = settings.ADDERMOBI_API_PASSWORD

    if upstream_credential_missing(username, password):
        msg = "跳过: Addermobi API 未配置（请在 .env 设置 ADDERMOBI_API_USERNAME / PASSWORD）"
        logger.warning(msg)
        set_task_result(ADDERMOBI_API_TASK_NAME, msg)
        return

    # 获取应用配置时区的当前时间（用于日志记录）
    app_time = datetime.now(APP_TIMEZONE)
    current_time_str = app_time.strftime("%Y-%m-%d %H:%M:%S")

    # 记录任务开始执行的日志（只记录一次）
    logger.info(f"{ADDERMOBI_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")

    try:
        # ============================================
        # 任务主逻辑开始
        # ============================================

        token_post = {
            "userName": username,
            "password": password
        }

        login_json = await post_json(
            "https://api.addermobi.com/api/User/loginApi",
            json_body=token_post,
            headers=Headers,
            label="Addermobi Login API",
            verify=False,
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
        Headers["Authorization"] = f"Bearer {access_token}"

        # 修改日期计算逻辑
        if start_date:
            # 使用传入的日期
            if end_date:
                start_date_str = start_date
                end_date_str = end_date
            else:
                # 如果没有提供end_date，使用start_date
                start_date_str = start_date
                end_date_str = start_date
        else:
            # 原有的自动计算逻辑
            app_now = datetime.now(APP_TIMEZONE)
            app_yesterday = app_now - timedelta(days=1)
            yesterday_str = app_yesterday.strftime("%Y-%m-%d")
            today_str = app_now.strftime("%Y-%m-%d")

            if 0 <= app_now.hour <= 2:
                start_date_str = yesterday_str
                end_date_str = today_str
            else:
                start_date_str = today_str
                end_date_str = today_str

        # Addermobi API使用两个条件：大于等于起始日期，小于等于结束日期
        p1 = [
            {"name": "Revenue_time", "value": start_date_str, "displayType": "thanorequal"},
            {"name": "Revenue_time", "value": end_date_str, "displayType": "lessorequal"}
        ]

        tbsj_params = {
            "page": 1,
            "rows": 1000,
            "sort": "Revenue_time,Product_id",
            "order": "desc",
            "wheres": json.dumps(p1)
        }
        ad_data = await fetch_addermobi_rows(
            url="https://api.addermobi.com/api/Revenue_DetailReports/GetData",
            payload=tbsj_params,
            headers=Headers,
        )
        await import_upstream_ad_data(
            task_name=ADDERMOBI_API_TASK_NAME,
            data=ad_data,
            field_mapping={
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
            },
            source="Addermobi定时任务",
            current_time_str=current_time_str,
            notify_title="Addermobi",
            data_transform=preprocess_addermobi_match_counts,
        )

    except Exception as e:
        # ========== 全局错误处理 ==========
        error_msg = f"{ADDERMOBI_API_TASK_NAME} 执行失败: {str(e)}"
        # 记录详细错误信息（包括完整的堆栈跟踪）
        logger.error(error_msg, exc_info=True)
        # 同时使用 logger.warning 确保即使日志级别设置为 WARNING 也能看到错误信息
        logger.warning(f"[Addermobi API获取数据] {error_msg}")
        raise
