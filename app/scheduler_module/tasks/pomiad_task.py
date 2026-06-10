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
from app.core.config import settings
from app.scheduler_module.task_names import POMIAD_API_TASK_NAME
from app.scheduler_module.task_utils import resolve_upstream_date_range
from app.scheduler_module.upstream_fetch import fetch_pomiad_rows
from app.scheduler_module.upstream_task_runner import run_upstream_import_task

# Pomiad data_detail → 平台标准字段 → 前端 AdData 列表头（frontend/src/views/AdData.vue）
POMIAD_FIELD_MAPPING = {
    "date": "data_date_f",
    "product_name": "domain_name",
    "ad_unit": "ad_unit_name",
    "country_code": "country_name",
    "request_count": "ad_request",
    "match_count": "match_count",
    "display_count": "imps",
    "click_count": "clicks",
    "revenue_before_deduct": "final_revenue",
    "ecpm_before_deduct": "cpm",
    "cpc": "cpc",
}

_POMIAD_EMPTY_COUNTRY_NAMES = frozenset({"n/a", "na", "unknown", "-", "none"})


def preprocess_pomiad_rows(ad_data: list) -> list:
    """Pomiad 行数据预处理：补全产品域名、清洗无效国家名。"""
    for item in ad_data:
        if not str(item.get("domain_name") or "").strip():
            item["domain_name"] = (item.get("site") or "").strip()
        country_name = str(item.get("country_name") or "").strip()
        if country_name.lower() in _POMIAD_EMPTY_COUNTRY_NAMES:
            item["country_name"] = ""
    return ad_data


async def pomiad_api_task(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Pomiad 定时任务：拉取 API 数据 → 预处理 → 标准入库。"""
    username = settings.POMIAD_API_USERNAME
    password = settings.POMIAD_API_PASSWORD
    base_url = settings.POMIAD_API_BASE_URL

    async def fetch_data():
        pomiad_start, pomiad_end = resolve_upstream_date_range(
            start_date,
            end_date,
            early_morning_dual_day=True,
        )
        return await fetch_pomiad_rows(
            base_url=base_url,
            username=username,
            password=password,
            start=pomiad_start,
            end=pomiad_end,
            is_by_country=settings.POMIAD_IS_BY_COUNTRY,
            api_data_limit=settings.POMIAD_API_DATA_LIMIT,
        )

    await run_upstream_import_task(
        POMIAD_API_TASK_NAME,
        credentials=(username, password),
        skip_hint="跳过: Pomiad API 未配置（请在 .env 设置 POMIAD_API_USERNAME / POMIAD_API_PASSWORD）",
        fetch_data=fetch_data,
        field_mapping=POMIAD_FIELD_MAPPING,
        source="Pomiad定时任务",
        notify_title="Pomiad",
        data_transform=preprocess_pomiad_rows,
        log_label="Pomiad API获取数据",
    )
