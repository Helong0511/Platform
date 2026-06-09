"""
TQT 上游广告数据拉取定时任务。

功能说明：
- 从 TQT API 按日期拉取广告明细，字段映射后经 upstream_import 去重入库
- 凭证缺失时跳过并写入任务结果说明

在系统中的位置：
- 由 TQT_API_TASK_NAME 调度；HTTP 见 upstream_fetch/upstream_http

注意事项：
1. .env 须配置 TQT 相关账号密码与 endpoint
2. 拉取日期范围默认昨天至今，避免重复全量扫
"""
import hashlib
import logging
from datetime import datetime, timedelta

import pytz

from app.core.config import settings
from app.scheduler_module.task_names import TQT_API_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.task_utils import upstream_credential_missing
from app.scheduler_module.upstream_fetch import fetch_tqt_rows
from app.scheduler_module.upstream_import import import_upstream_ad_data

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)


# 应用时区配置（从统一配置读取）
# 用于将本地时间转换为标准时区
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)

# TQT API配置
tqt_url = 'https://union.e-kivi.com/open/api/report/data'  # TQT API的基础URL
tqt_app_key = settings.TQT_APP_KEY
tqt_api_secret = settings.TQT_API_SECRET

# HTTP请求头配置
Headers = {'Content-Type': 'application/json; charset=utf-8'}


def generate_sign(params: dict, api_secret: str = tqt_api_secret) -> str:
    """
    根据参数和API密钥生成MD5签名
    
    签名生成规则（TQT API要求）：
    1. 按参数名 ASCII 升序排序（排除 sign 参数本身）
    2. 将所有参数拼接成 key + value 的字符串（无分隔符）
    3. 在拼接后的字符串首尾都拼接 apiSecret
    4. 将整个字符串全部转为小写
    5. 对字符串进行 MD5 加密，结果转为小写字符串
    
    参数:
        params: 需要签名的参数字典
        api_secret: API密钥，默认使用全局配置的密钥
    
    返回:
        str: MD5签名字符串（小写）
    """
    # 步骤1：过滤掉sign参数，并按参数名ASCII升序排序
    # 这样确保相同参数生成的签名一致
    sorted_items = sorted((k, v) for k, v in params.items() if k != "sign")

    # 步骤2：将所有参数拼接成 key + value 的字符串（无分隔符）
    query_str = "".join(f"{k}{v}" for k, v in sorted_items)

    # 步骤3：在首尾拼接 apiSecret，并转为小写
    # 格式：apiSecret + 参数字符串 + apiSecret
    full_str = f"{api_secret}{query_str}{api_secret}".lower()

    # 步骤4：对字符串进行MD5加密，并转为小写十六进制字符串
    md5_hash = hashlib.md5(full_str.encode("utf-8")).hexdigest().lower()
    return md5_hash


async def tqt_api_task(
        start_date: str | None = None,
        end_date: str | None = None
) -> None:
    """
    TQT定时任务主函数
    
    参数:
        start_date: 可选，起始日期 (格式: YYYY-MM-DD)，如果不提供则根据时间自动选择
        end_date: 可选，结束日期 (格式: YYYY-MM-DD)，如果不提供则使用start_date
    """
    # 获取应用配置时区的当前时间（用于日志记录）
    app_time = datetime.now(APP_TIMEZONE)
    current_time_str = app_time.strftime("%Y-%m-%d %H:%M:%S")

    # 记录任务开始执行的日志（只记录一次）
    logger.info(f"{TQT_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")

    if upstream_credential_missing(tqt_app_key, tqt_api_secret):
        msg = "跳过: TQT API 未配置（请在 .env 设置 TQT_APP_KEY / TQT_API_SECRET）"
        logger.warning(msg)
        set_task_result(TQT_API_TASK_NAME, msg)
        return

    try:
        # ============================================
        # 任务主逻辑开始
        # ============================================

        # 构建TQT API请求参数
        if start_date:
            # 使用传入的日期
            if end_date:
                tqt_start_date = start_date
                tqt_end_date = end_date
            else:
                # 如果没有提供end_date，使用start_date
                tqt_start_date = start_date
                tqt_end_date = start_date
        else:
            # 原有的自动计算逻辑
            app_now = datetime.now(APP_TIMEZONE)
            app_yesterday = app_now - timedelta(days=1)
            yesterday_str = app_yesterday.strftime("%Y-%m-%d")
            today_str = app_now.strftime("%Y-%m-%d")

            if 0 <= app_now.hour <= 2:
                tqt_start_date = yesterday_str
                tqt_end_date = today_str
            else:
                tqt_start_date = today_str
                tqt_end_date = today_str

        tqt_params = {
            "appKey": tqt_app_key,
            "startDate": tqt_start_date,
            "endDate": tqt_end_date,
            "page": 1,
            "pageSize": 1000,
            "type": "country"
        }

        # 生成API签名（TQT API要求所有请求都必须包含签名）
        sign = generate_sign(tqt_params, tqt_api_secret)
        # 将签名添加到请求参数中
        tqt_params['sign'] = sign

        data = await fetch_tqt_rows(
            url=tqt_url,
            params=tqt_params,
            headers=Headers,
        )
        await import_upstream_ad_data(
            task_name=TQT_API_TASK_NAME,
            data=data,
            field_mapping={
                "date": "date",
                "ad_unit": "ad_unit",
                "product_name": "url",
                "country_code": "country_code",
                "request_count": "requests",
                "match_count": "matche_que",
                "display_count": "adimpressions",
                "click_count": "clicks",
                "revenue_before_deduct": "estirevenue",
                "ecpm_before_deduct": "ecpm",
                "coverage_rate": "coverage",
                "display_rate": "display_rate",
                "click_rate": "ctr",
            },
            source="TQT定时任务",
            current_time_str=current_time_str,
            notify_title="TQT",
        )

    except Exception as e:
        # ========== 全局错误处理 ==========

        # 捕获任务执行过程中的任何异常
        # 注意：如果任务执行失败，异常会被捕获并记录
        # 定时任务调度器的锁机制会自动释放，错误信息会保存到数据库

        error_msg = f"{TQT_API_TASK_NAME} 执行失败: {str(e)}"
        # 记录详细错误信息（包括完整的堆栈跟踪）
        logger.error(error_msg, exc_info=True)
        # 同时使用 logger.warning 确保即使日志级别设置为 WARNING 也能看到错误信息
        logger.warning(f"[TQT获取广告数据] {error_msg}")

        # 重新抛出异常，让定时任务调度器的锁机制能够记录错误状态
        # 这样可以在数据库中标记任务执行失败，便于后续排查问题
        raise
