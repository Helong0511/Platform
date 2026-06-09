"""
Pomiad 上游广告数据拉取定时任务。

功能说明：
- 从 Pomiad API 拉取广告明细，字段映射后经 upstream_import 去重入库
- 未配置 POMIAD_API_USERNAME/PASSWORD 时跳过并写入说明

在系统中的位置：
- 由 POMIAD_API_TASK_NAME 调度

注意事项：
1. 拉数日期默认按上游报表时区解析
2. 有新增/更新时 upstream_import 会发 Telegram，注意通知频率
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

# 应用时区（与配置 TIMEZONE 一致，用于日志与通知时间展示）
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)

# Pomiad data_detail → 平台标准字段 → 前端 AdData 列表头（frontend/src/views/AdData.vue）
# 格式：平台字段 → Pomiad API 字段 | 前端列名
POMIAD_FIELD_MAPPING = {
    "date": "data_date_f",                    # 前端「数据日期」← data_date_f
    "product_name": "domain_name",            # 前端「产品名称」← domain_name（空时回退 site）
    "ad_unit": "ad_unit_name",                # 前端「广告单元」← ad_unit_name
    "country_code": "country_name",           # 前端「国家」← country_name（展示为 country_name_zh）
    "request_count": "ad_request",            # 前端「请求数」← ad_request
    "match_count": "match_count",             # 前端「匹配数」← match_count
    "display_count": "imps",                  # 前端「展示数」← imps
    "click_count": "clicks",                  # 前端「点击数」← clicks
    "revenue_before_deduct": "final_revenue", # 前端「收益」(管理员) ← final_revenue（分成后）
    "ecpm_before_deduct": "cpm",              # 前端「eCPM」(管理员) ← cpm
    "cpc": "cpc",                             # 前端「CPC」← cpc
    # 未映射、入库后自动计算：覆盖率、展示率、点击率（coverage_rate / display_rate / click_rate）
    # 未映射、按产品减扣比例计算：收益(扣)、eCPM(扣)（revenue_after_deduct / ecpm_after_deduct）
}


def preprocess_pomiad_rows(ad_data: list) -> list:
    """
    Pomiad 行数据预处理：补全产品域名。

    当 domain_name 为空时，回退使用 API 返回的 site 字段作为域名，
    保证入库时产品维度可关联。

    参数:
        ad_data: fetch_pomiad_rows 返回的原始行列表（就地修改）

    返回:
        处理后的同一列表引用
    """
    for item in ad_data:
        if not str(item.get("domain_name") or "").strip():
            item["domain_name"] = (item.get("site") or "").strip()
    return ad_data


async def pomiad_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """
    Pomiad 定时任务主函数。

    流程：校验凭证 → 解析日期范围 → 拉取 API 数据 → 预处理 → 标准入库。

    参数:
        start_date: 可选起始日期 (YYYY-MM-DD)；未提供时由 resolve_upstream_date_range 按调度时刻推算
        end_date: 可选结束日期 (YYYY-MM-DD)；未提供时与 start_date 或默认策略一致

    异常:
        拉数或入库失败时记录错误日志并重新抛出，由调度器标记任务失败
    """
    # ========== Pomiad API 配置 ==========
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
        # ============================================
        # 任务主逻辑：拉数 + 入库
        # ============================================

        # ---------- 日期范围（凌晨可能拉取昨日+今日双日数据） ----------
        pomiad_start, pomiad_end = resolve_upstream_date_range(
            start_date,
            end_date,
            early_morning_dual_day=True,
        )

        # ---------- 调用 Pomiad API ----------
        data = await fetch_pomiad_rows(
            base_url=base_url,
            username=username,
            password=password,
            start=pomiad_start,
            end=pomiad_end,
            is_by_country=settings.POMIAD_IS_BY_COUNTRY,
            api_data_limit=settings.POMIAD_API_DATA_LIMIT,
        )

        # ---------- 标准上游入库（含 domain 预处理与 Telegram 通知） ----------
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
