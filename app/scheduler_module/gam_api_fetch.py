"""
Google Ad Manager（GAM）API 联调脚本。

用途
----
1. 验证 GCP 服务账号密钥能否成功访问 GAM（Google Ad Manager / 原 DFP）
2. 全面拉取多维度报表：广告单元 / 国家+广告单元 / 站点+广告单元 / 按日汇总
3. 每份报表包含请求、匹配、展示、点击、收入等全部可用指标
4. 将 API 返回的**全部行**保存为本地 CSV（原始）与 JSON（结构化）

凭证与账号（默认值，均可被环境变量覆盖）
----------------------------------------
默认加载两个 GAM 账号（见 DEFAULT_GAM_ACCOUNTS）：
- secrets/gam-23347342743.json → network 23347342743 / X BROWSER LIMITED
- secrets/gam-23348711678.json → network 23348711678 / Leadwin

network_code 从密钥文件名 ``gam-{network_code}.json`` 自动解析。
application_name 优先取账号配置 / 密钥 JSON 可选字段，否则回退为 network_code。

环境变量
--------
  GAM_ACCOUNTS           JSON 账号列表（覆盖默认多账号）；credentials_json 必填，
                         application_name / network_code 均可省略（自动解析）
  GAM_ACCOUNT            仅拉指定账号，逗号分隔，匹配 key 或 network_code
  GAM_CREDENTIALS_JSON   单账号模式：服务账号 JSON 路径
  GAM_APPLICATION_NAME   单账号模式：可选，覆盖自动解析的应用名称
  GAM_NETWORK_CODE       单账号模式：可选，覆盖从文件名解析的网络代码
  GAM_API_VERSION        API 版本，默认 v202605
  GAM_START_DATE         开始日期 YYYY-MM-DD，默认昨天
  GAM_END_DATE           结束日期 YYYY-MM-DD，默认与开始日期相同
  GAM_OUTPUT_DIR         输出目录，默认 tests/API/gam_output（联调脚本）
  GAM_REPORTS            逗号分隔报表键，默认全部（ad_unit,country,site,daily）
  GAM_PRODUCT_WHITELIST  单账号模式：逗号分隔产品名；非空时仅保留白名单内 product_name

产品白名单（按账号配置）
------------------------
每个账号可设置 product_whitelist（或 product_names 逗号串）：
- 非空：仅保留 product_name 在白名单内的**叶子广告单元**行（大小写不敏感，自动忽略 www. 前缀）
- 为空或未设置：保留全部产品（不过滤）
- 未在配置中写 product_whitelist 时，若密钥路径匹配 DEFAULT_GAM_ACCOUNTS，则继承内置白名单
- daily 报表无产品维度，白名单非空时会跳过

DEFAULT_GAM_ACCOUNTS / GAM_ACCOUNTS JSON 示例：
  "product_whitelist": ["worldpuzzle.io", "buildascamempire.com"]

运行示例
--------
  pip install googleads
  python -m app.scheduler_module.gam_api_fetch

仅拉 Leadwin 账号：
  set GAM_ACCOUNT=leadwin
  python -m app.scheduler_module.gam_api_fetch

仅拉指定 network code：
  set GAM_ACCOUNT=23348711678
  python -m app.scheduler_module.gam_api_fetch

单账号覆盖（兼容旧用法；network_code / application_name 均可自动解析）：
  set GAM_CREDENTIALS_JSON=secrets/gam-23347342743.json
  python -m app.scheduler_module.gam_api_fetch

自定义多账号 JSON：
  set GAM_ACCOUNTS=[{"key":"leadwin","credentials_json":"secrets/gam-23348711678.json","application_name":"Leadwin"}]
  python -m app.scheduler_module.gam_api_fetch

拉取多天并保存：
  set GAM_START_DATE=2026-06-01
  set GAM_END_DATE=2026-06-30
  python -m app.scheduler_module.gam_api_fetch

仅拉广告单元报表：
  set GAM_REPORTS=ad_unit
  python -m app.scheduler_module.gam_api_fetch

输出说明
--------
- 文件名前缀：gam_{network_code}_{report_key}_{日期范围}_{时间戳}.csv/.json
- manifest：gam_manifest_{network_code}_{日期范围}_{时间戳}.json
- CSV：GAM 原始导出，字段名如 Dimension.DATE、Column.TOTAL_LINE_ITEM_LEVEL_IMPRESSIONS
- JSON：GAM 原始列名；另存 *_mapped.json 为全量业务字段（含全部维度/指标 + 平台别名）
- 收入字段 *REVENUE* / *CPM_AND_CPC_REVENUE* 为微单位，÷ 1_000_000 为 USD
- GAM 会省略全零列；脚本会在 CSV/JSON 中自动补 \"0\"，保证列完整
"""
from __future__ import annotations

import csv
import io
import json
import locale
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Windows UTF-8 兼容（须在 import googleads 之前执行）
# ---------------------------------------------------------------------------

def _ensure_utf8_environment() -> None:
    """
    在 Windows 中文环境（默认 cp936）下，googleads 初始化时会检测 locale 并打印警告。

    本函数在导入 googleads 之前：
    1. 设置 PYTHONUTF8 / PYTHONIOENCODING，便于子进程与 IO 使用 UTF-8
    2. 尝试将系统 locale 切到 UTF-8
    3. 将 stdout/stderr 重配置为 utf-8，避免控制台中文乱码
    4. 修补 locale.getdefaultlocale，避免 googleads 在已用 UTF-8 时仍误报 cp936
    """
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    if sys.platform == "win32":
        for loc in (".UTF-8", "en_US.UTF-8", "C.UTF-8"):
            try:
                locale.setlocale(locale.LC_ALL, loc)
                break
            except locale.Error:
                continue

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    # googleads 内部调用已废弃的 getdefaultlocale()；Windows 下常返回 cp936 导致误报
    if not getattr(locale, "_gam_utf8_patched", False):
        _orig_getdefaultlocale = locale.getdefaultlocale

        def _utf8_getdefaultlocale(category=locale.LC_ALL):
            if sys.platform == "win32":
                lang, enc = locale.getlocale(category)
                if lang:
                    # getlocale 示例：('Chinese (Simplified)_China', 'utf8')
                    lang = lang.split(".")[0].split("_")[0] if "_" in lang else "zh_CN"
                return lang or "zh_CN", "UTF-8"
            return _orig_getdefaultlocale(category)

        locale.getdefaultlocale = _utf8_getdefaultlocale  # type: ignore[method-assign]
        locale._gam_utf8_patched = True  # type: ignore[attr-defined]


# 模块加载时立即执行，保证后续 from googleads 不再触发编码警告
_ensure_utf8_environment()

# ---------------------------------------------------------------------------
# 路径与默认配置常量
# ---------------------------------------------------------------------------

# 项目根目录：app/scheduler_module/gam_api_fetch.py → parents[2] = Platform/
ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)

# GCP 服务账号密钥目录
SECRETS_DIR = ROOT / "secrets"

# 默认多账号配置；network_code 从密钥文件名 gam-{network_code}.json 自动解析
# product_whitelist 非空时仅保留对应 product_name；空列表表示全量
DEFAULT_GAM_ACCOUNTS: list[dict[str, str | list[str]]] = [
    {
        "key": "x_browser",
        "credentials_json": "secrets/gam-23347342743.json",
        "application_name": "X BROWSER LIMITED",
        "product_whitelist": [
            "puzzlegames.shop",
            "iogames.quest",
            "casualgames.quest",
            "thestrategygames.shop",
            "play2048games.shop"
        ]
    },
    {
        "key": "leadwin",
        "credentials_json": "secrets/gam-23348711678.json",
        "application_name": "Leadwin",
        "product_whitelist": []
    },
]

# 单账号模式默认密钥（GAM_CREDENTIALS_JSON 未设置时使用）
DEFAULT_CREDENTIALS = SECRETS_DIR / "gam-23347342743.json"

# 报表 CSV/JSON 默认输出目录
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "gam_output"

# 密钥文件名约定：gam-{network_code}.json
GAM_CREDENTIALS_FILENAME_PATTERN = re.compile(r"^gam-(\d+)\.json$", re.I)

# 密钥 JSON 内可选的 application_name 字段（非 GCP 标准字段，可自行添加）
GAM_CREDENTIALS_APP_NAME_KEYS = (
    "application_name",
    "applicationName",
    "admanager_application_name",
)

# Ad Manager SOAP API 版本（googleads 支持的版本之一，过旧会报 Unrecognized version）
DEFAULT_API_VERSION = "v202605"

# 请求/匹配类指标（仅在与广告单元相关的部分维度下可用）
GAM_REQUEST_COLUMNS = [
    "TOTAL_AD_REQUESTS",
    "TOTAL_CODE_SERVED_COUNT",
    "AD_EXCHANGE_TOTAL_REQUESTS",
    "AD_EXCHANGE_RESPONSES_SERVED",
]

# 展示/点击/收入类指标（各维度通用）
GAM_DELIVERY_COLUMNS = [
    "TOTAL_LINE_ITEM_LEVEL_IMPRESSIONS",
    "TOTAL_LINE_ITEM_LEVEL_CLICKS",
    "TOTAL_LINE_ITEM_LEVEL_CPM_AND_CPC_REVENUE",
    "AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS",
    "AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS",
    "AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE",
    "TOTAL_INVENTORY_LEVEL_IMPRESSIONS",
    "TOTAL_INVENTORY_LEVEL_CLICKS",
    "TOTAL_INVENTORY_LEVEL_CPM_AND_CPC_REVENUE",
]

# Active View 可见率（Historical 报表，与 Ad Exchange 维度兼容）
GAM_VIEWABILITY_COLUMNS = [
    "AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS",
    "AD_EXCHANGE_ACTIVE_VIEW_MEASURABLE_IMPRESSIONS",
    "AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS_RATE",
]

# 全量指标（请求 + 投放 + 可见率）
GAM_FULL_COLUMNS = GAM_REQUEST_COLUMNS + GAM_DELIVERY_COLUMNS + GAM_VIEWABILITY_COLUMNS

# 站点维度不支持 TOTAL_AD_REQUESTS，其余请求类指标可用
GAM_SITE_REQUEST_COLUMNS = [
    "TOTAL_CODE_SERVED_COUNT",
    "AD_EXCHANGE_TOTAL_REQUESTS",
    "AD_EXCHANGE_RESPONSES_SERVED",
]
GAM_SITE_COLUMNS = GAM_SITE_REQUEST_COLUMNS + GAM_DELIVERY_COLUMNS + GAM_VIEWABILITY_COLUMNS

# GAM 收入列为微单位（USD × 1_000_000）
GAM_REVENUE_MICRO_DIVISOR = 1_000_000

# GAM Column → (平台 ad_data 字段名, 中文说明)
GAM_BUSINESS_METRIC_MAPPING: dict[str, tuple[str, str]] = {
    "Column.AD_EXCHANGE_TOTAL_REQUESTS": ("request_count", "请求数"),
    "Column.AD_EXCHANGE_RESPONSES_SERVED": ("match_count", "匹配请求数"),
    "Column.AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS": ("display_count", "展示数"),
    "Column.AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS": ("click_count", "点击数"),
    "Column.AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE": ("revenue_before_deduct", "收益"),
    "Column.AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS_RATE": (
        "viewability_rate",
        "可见率",
    ),
}

# 平台字段别名 → mapped 中对应的全量指标字段名（snake_case）
GAM_PLATFORM_METRIC_ALIASES: dict[str, str] = {
    "request_count": "ad_exchange_total_requests",
    "match_count": "ad_exchange_responses_served",
    "display_count": "ad_exchange_line_item_level_impressions",
    "click_count": "ad_exchange_line_item_level_clicks",
    "revenue_before_deduct": "ad_exchange_line_item_level_revenue",
    "viewability_rate": "ad_exchange_active_view_viewable_impressions_rate",
}

# GAM Dimension → 平台字段名
GAM_DIMENSION_MAPPING: dict[str, str] = {
    "Dimension.DATE": "date",
    "Dimension.AD_UNIT_NAME": "ad_unit",
    "Dimension.AD_UNIT_ID": "ad_unit_id",
    "Dimension.COUNTRY_CODE": "country_code",
    "Dimension.SITE_NAME": "site_name",
}

# 平台衍生指标：无 GAM 直出列，按 ad_data.calculate_rates / ad_data_processor 公式计算
# 字段名 → (中文说明, 计算公式)
GAM_DERIVED_METRIC_FORMULAS: dict[str, tuple[str, str]] = {
    "coverage_rate": ("覆盖率", "match_count / request_count × 100"),
    "display_rate": ("展示率", "display_count / match_count × 100"),
    "click_rate": ("点击率", "click_count / display_count × 100"),
    "ecpm_before_deduct": ("eCPM未减扣", "revenue_before_deduct / display_count × 1000"),
    "cpc": ("CPC", "revenue_before_deduct / click_count"),
}

# GAM 当前无法由报表直接提供的 ad_data 字段
GAM_UNAVAILABLE_PLATFORM_FIELDS: dict[str, str] = {
    "pageviews": "PageViews（GAM 报表无此原生列，需 GA 等数据源）",
    "revenue_after_deduct": "收益已减扣（需平台扣减规则）",
    "ecpm_after_deduct": "eCPM已减扣（需平台扣减规则）",
}

# ---------------------------------------------------------------------------
# GAM ↔ 平台 ad_data 完整字段映射目录
# mapping_type 说明：
#   direct          → 直写 ad_data 同名字段
#   alias           → mapped 平台别名，源自下方 source_mapped_field
#   derived         → 脚本按公式计算后写入 ad_data
#   import_transform→ 入库前转换（如 product_name → product_id）
#   auxiliary       → 仅保留在 mapped/原始 JSON，不入 ad_data
#   platform_only   → ad_data 有字段但 GAM 无来源
# ---------------------------------------------------------------------------
GAM_PLATFORM_MAPPING_CATALOG: list[dict[str, str]] = [
    # —— 维度 ——
    {
        "category": "dimension",
        "gam_key": "Dimension.DATE",
        "mapped_field": "date",
        "platform_model": "ad_data",
        "platform_field": "date",
        "mapping_type": "direct",
        "transform": "ISO 日期字符串，入库时 normalize_date_for_ad_data",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "dimension",
        "gam_key": "Dimension.AD_UNIT_NAME",
        "mapped_field": "ad_unit",
        "platform_model": "ad_data",
        "platform_field": "ad_unit",
        "mapping_type": "direct",
        "transform": "normalize_ad_unit；最长 100 字符，超长需截断",
        "reports": "ad_unit,country,site",
    },
    {
        "category": "dimension",
        "gam_key": "Dimension.AD_UNIT_ID",
        "mapped_field": "ad_unit_id",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "GAM 自动附带，用于去重/对账，不入 ad_data",
        "reports": "ad_unit,country,site",
    },
    {
        "category": "dimension",
        "gam_key": "Dimension.COUNTRY_CODE",
        "mapped_field": "country_code",
        "platform_model": "ad_data",
        "platform_field": "country_code",
        "mapping_type": "direct",
        "transform": "ISO-2；入库走 find_country_code_by_any_format",
        "reports": "country",
    },
    {
        "category": "dimension",
        "gam_key": "Dimension.SITE_NAME",
        "mapped_field": "site_name",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "有效站点名可直作 product_name；(unknown) 时回退 ad_unit 解析",
        "reports": "site",
    },
    # —— 请求/匹配指标 ——
    {
        "category": "metric",
        "gam_key": "Column.TOTAL_AD_REQUESTS",
        "mapped_field": "total_ad_requests",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "全渠道广告请求（含非 Ad Exchange），与 request_count 口径不同",
        "reports": "ad_unit,country,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.TOTAL_CODE_SERVED_COUNT",
        "mapped_field": "total_code_served_count",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "代码调用次数，平台无对应列",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.AD_EXCHANGE_TOTAL_REQUESTS",
        "mapped_field": "ad_exchange_total_requests",
        "platform_model": "ad_data",
        "platform_field": "request_count",
        "mapping_type": "alias",
        "transform": "微单位整数；平台别名 request_count",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.AD_EXCHANGE_RESPONSES_SERVED",
        "mapped_field": "ad_exchange_responses_served",
        "platform_model": "ad_data",
        "platform_field": "match_count",
        "mapping_type": "alias",
        "transform": "平台别名 match_count",
        "reports": "ad_unit,country,site,daily",
    },
    # —— 展示/点击/收入（全渠道 + Ad Exchange）——
    {
        "category": "metric",
        "gam_key": "Column.TOTAL_LINE_ITEM_LEVEL_IMPRESSIONS",
        "mapped_field": "total_line_item_level_impressions",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "含直客/订单展示，通常大于 Ad Exchange 展示",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.TOTAL_LINE_ITEM_LEVEL_CLICKS",
        "mapped_field": "total_line_item_level_clicks",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "全渠道点击",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.TOTAL_LINE_ITEM_LEVEL_CPM_AND_CPC_REVENUE",
        "mapped_field": "total_line_item_level_cpm_and_cpc_revenue",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "收入微单位 ÷1_000_000；全渠道收益",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS",
        "mapped_field": "ad_exchange_line_item_level_impressions",
        "platform_model": "ad_data",
        "platform_field": "display_count",
        "mapping_type": "alias",
        "transform": "平台别名 display_count",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS",
        "mapped_field": "ad_exchange_line_item_level_clicks",
        "platform_model": "ad_data",
        "platform_field": "click_count",
        "mapping_type": "alias",
        "transform": "平台别名 click_count",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE",
        "mapped_field": "ad_exchange_line_item_level_revenue",
        "platform_model": "ad_data",
        "platform_field": "revenue_before_deduct",
        "mapping_type": "alias",
        "transform": "微单位 ÷1_000_000；平台别名 revenue_before_deduct",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.TOTAL_INVENTORY_LEVEL_IMPRESSIONS",
        "mapped_field": "total_inventory_level_impressions",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "库存层级展示；纯 Ad Exchange 账号常为 0",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.TOTAL_INVENTORY_LEVEL_CLICKS",
        "mapped_field": "total_inventory_level_clicks",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "库存层级点击",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.TOTAL_INVENTORY_LEVEL_CPM_AND_CPC_REVENUE",
        "mapped_field": "total_inventory_level_cpm_and_cpc_revenue",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "库存层级收入（微单位 ÷1_000_000）",
        "reports": "ad_unit,country,site,daily",
    },
    # —— 可见率 ——
    {
        "category": "metric",
        "gam_key": "Column.AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS",
        "mapped_field": "ad_exchange_active_view_viewable_impressions",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "可见展示次数；平台仅存 viewability_rate 比率",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.AD_EXCHANGE_ACTIVE_VIEW_MEASURABLE_IMPRESSIONS",
        "mapped_field": "ad_exchange_active_view_measurable_impressions",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "可测展示次数",
        "reports": "ad_unit,country,site,daily",
    },
    {
        "category": "metric",
        "gam_key": "Column.AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS_RATE",
        "mapped_field": "ad_exchange_active_view_viewable_impressions_rate",
        "platform_model": "ad_data",
        "platform_field": "viewability_rate",
        "mapping_type": "alias",
        "transform": "GAM 可能为比例或百分比，脚本统一为 %；别名 viewability_rate",
        "reports": "ad_unit,country,site,daily",
    },
    # —— 衍生指标（mapped 输出，入库写 ad_data）——
    {
        "category": "derived",
        "gam_key": "",
        "mapped_field": "coverage_rate",
        "platform_model": "ad_data",
        "platform_field": "coverage_rate",
        "mapping_type": "derived",
        "transform": "match_count / request_count × 100",
        "reports": "全部（有 request/match 时）",
    },
    {
        "category": "derived",
        "gam_key": "",
        "mapped_field": "display_rate",
        "platform_model": "ad_data",
        "platform_field": "display_rate",
        "mapping_type": "derived",
        "transform": "display_count / match_count × 100",
        "reports": "全部",
    },
    {
        "category": "derived",
        "gam_key": "",
        "mapped_field": "click_rate",
        "platform_model": "ad_data",
        "platform_field": "click_rate",
        "mapping_type": "derived",
        "transform": "click_count / display_count × 100",
        "reports": "全部",
    },
    {
        "category": "derived",
        "gam_key": "",
        "mapped_field": "ecpm_before_deduct",
        "platform_model": "ad_data",
        "platform_field": "ecpm_before_deduct",
        "mapping_type": "derived",
        "transform": "revenue_before_deduct / display_count × 1000",
        "reports": "全部",
    },
    {
        "category": "derived",
        "gam_key": "",
        "mapped_field": "cpc",
        "platform_model": "ad_data",
        "platform_field": "cpc",
        "mapping_type": "derived",
        "transform": "revenue_before_deduct / click_count",
        "reports": "全部",
    },
    # —— 入库元数据 / 转换 ——
    {
        "category": "meta",
        "gam_key": "",
        "mapped_field": "network_code",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "账号网络代码，用于多账号文件区分",
        "reports": "全部",
    },
    {
        "category": "meta",
        "gam_key": "",
        "mapped_field": "report_key",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "报表类型 ad_unit/country/site/daily",
        "reports": "全部",
    },
    {
        "category": "meta",
        "gam_key": "",
        "mapped_field": "is_leaf_ad_unit",
        "platform_model": "",
        "platform_field": "",
        "mapping_type": "auxiliary",
        "transform": "是否叶子广告单元；入库建议仅 is_leaf_ad_unit=true",
        "reports": "含 ad_unit 维度时",
    },
    {
        "category": "meta",
        "gam_key": "",
        "mapped_field": "product_name",
        "platform_model": "products",
        "platform_field": "name",
        "mapping_type": "import_transform",
        "transform": "入库时解析为 product_id（products.name 匹配）",
        "reports": "ad_unit,country,site",
    },
    # —— 平台 ad_data 有字段、GAM 无直出 ——
    {
        "category": "platform_only",
        "gam_key": "",
        "mapped_field": "",
        "platform_model": "ad_data",
        "platform_field": "product_id",
        "mapping_type": "import_transform",
        "transform": "由 product_name 查 products 表",
        "reports": "",
    },
    {
        "category": "platform_only",
        "gam_key": "",
        "mapped_field": "",
        "platform_model": "ad_data",
        "platform_field": "pageviews",
        "mapping_type": "platform_only",
        "transform": GAM_UNAVAILABLE_PLATFORM_FIELDS["pageviews"],
        "reports": "",
    },
    {
        "category": "platform_only",
        "gam_key": "",
        "mapped_field": "",
        "platform_model": "ad_data",
        "platform_field": "revenue_after_deduct",
        "mapping_type": "platform_only",
        "transform": GAM_UNAVAILABLE_PLATFORM_FIELDS["revenue_after_deduct"],
        "reports": "",
    },
    {
        "category": "platform_only",
        "gam_key": "",
        "mapped_field": "",
        "platform_model": "ad_data",
        "platform_field": "ecpm_after_deduct",
        "mapping_type": "platform_only",
        "transform": GAM_UNAVAILABLE_PLATFORM_FIELDS["ecpm_after_deduct"],
        "reports": "",
    },
]

# ad_data 表全部业务字段（不含 id/created_at/updated_at）
# 字段名 → 中文说明（与 app/models/client_product.py AdData 列注释一致）
AD_DATA_PLATFORM_FIELD_LABELS: dict[str, str] = {
    "date": "数据日期",
    "country_code": "国家代码（ISO 二字母；未识别时保留原始国名）",
    "product_id": "产品ID",
    "ad_unit": "广告单元",
    "request_count": "请求数",
    "match_count": "匹配数",
    "coverage_rate": "覆盖率（%）",
    "display_count": "展示数",
    "display_rate": "展示率（%）",
    "click_count": "点击数",
    "click_rate": "点击率（%）",
    "viewability_rate": "可见率（%）",
    "cpc": "CPC",
    "pageviews": "PageViews",
    "ecpm_before_deduct": "eCPM未减扣",
    "ecpm_after_deduct": "eCPM已减扣",
    "revenue_before_deduct": "收益未减扣",
    "revenue_after_deduct": "收益已减扣",
}

AD_DATA_PLATFORM_FIELDS: tuple[str, ...] = tuple(AD_DATA_PLATFORM_FIELD_LABELS.keys())


def _gam_catalog_gam_keys() -> set[str]:
    return {item["gam_key"] for item in GAM_PLATFORM_MAPPING_CATALOG if item.get("gam_key")}


def _analyze_gam_platform_mapping_gaps() -> dict:
    """
    对比 GAM 拉数列与平台 ad_data，输出缺口分析。

    Returns:
        auxiliary_gam_fields: GAM 有、仅 mapped 保留、不入 ad_data 的列
        unmapped_gam_columns: 已请求但目录未登记的 GAM 列
        platform_fields_without_gam: ad_data 字段无 GAM 来源
        ad_data_fields_covered: 可由 GAM 写入 ad_data 的字段
    """
    catalog_gam = _gam_catalog_gam_keys()
    requested_gam = {f"Column.{name}" for name in GAM_FULL_COLUMNS}
    requested_gam |= {f"Dimension.{name}" for name in ("DATE", "AD_UNIT_NAME", "COUNTRY_CODE", "SITE_NAME")}
    requested_gam.add("Dimension.AD_UNIT_ID")

    unmapped_gam = sorted(requested_gam - catalog_gam)
    auxiliary = [
        item for item in GAM_PLATFORM_MAPPING_CATALOG
        if item["mapping_type"] == "auxiliary" and item.get("gam_key")
    ]
    platform_covered: set[str] = set()
    for item in GAM_PLATFORM_MAPPING_CATALOG:
        field = item.get("platform_field") or ""
        if field and item["mapping_type"] in {"direct", "alias", "derived", "import_transform"}:
            if item["platform_model"] == "ad_data":
                platform_covered.add(field)
    platform_without_gam = [
        field for field in AD_DATA_PLATFORM_FIELDS if field not in platform_covered
    ]
    return {
        "ad_data_field_total": len(AD_DATA_PLATFORM_FIELDS),
        "ad_data_fields_covered_by_gam": sorted(platform_covered & set(AD_DATA_PLATFORM_FIELDS)),
        "ad_data_fields_without_gam_source": platform_without_gam,
        "gam_requested_column_count": len(requested_gam),
        "gam_catalog_entry_count": len(GAM_PLATFORM_MAPPING_CATALOG),
        "gam_columns_not_in_catalog": unmapped_gam,
        "gam_auxiliary_fields": [
            {
                "gam_key": item["gam_key"],
                "mapped_field": item["mapped_field"],
                "note": item["transform"],
            }
            for item in auxiliary
        ],
        "gam_auxiliary_count": len(auxiliary),
        "platform_alias_fields": dict(GAM_PLATFORM_METRIC_ALIASES),
    }


def _platform_mapping_for_manifest() -> dict:
    """供 manifest 输出的映射摘要。"""
    gaps = _analyze_gam_platform_mapping_gaps()
    by_type: dict[str, list[dict[str, str]]] = {}
    for item in GAM_PLATFORM_MAPPING_CATALOG:
        by_type.setdefault(item["mapping_type"], []).append(item)
    return {
        "catalog": GAM_PLATFORM_MAPPING_CATALOG,
        "by_mapping_type": by_type,
        "gap_analysis": gaps,
        "ad_data_platform_fields": {
            field: AD_DATA_PLATFORM_FIELD_LABELS[field]
            for field in AD_DATA_PLATFORM_FIELDS
        },
    }


# 支持解析/识别 product_name 的报表键（daily 全网络汇总无产品维度）
GAM_REPORT_KEYS_WITH_PRODUCT_NAME = frozenset({"ad_unit", "country", "site"})

# 定时任务默认拉取的报表（不含 daily）
GAM_SCHEDULER_REPORT_KEYS: tuple[str, ...] = ("ad_unit", "country", "site")

# 产品名称来源说明（对应平台 product_name / 智索 domain_name）
GAM_PRODUCT_NAME_SOURCES: dict[str, str] = {
    "site": "Dimension.SITE_NAME → product_name（站点域名）",
    "ad_unit": "从 AD_UNIT_NAME 解析：ume_/cy_{产品}_{日期}_… 或 {域名}_{类型} (ID)",
    "country": "从 AD_UNIT_NAME 解析：ume_/cy_{产品}_{日期}_… 或 {域名}_{类型} (ID)",
    "daily": "无产品维度（全网络按日汇总，不输出 product_name 列）",
}

# 叶子广告单元命名：{ume|cy}_{产品名}_{YYYYMMDD}_{类型}_{序号}
# 产品名取 ume_/cy_ 与 _YYYYMMDD_ 之间的片段，如 ume_buildascamempire.com_20260608_banner_1 → buildascamempire.com
GAM_AD_UNIT_LEAF_PATTERN = re.compile(r"(?:ume|cy)_(.+?)_\d{8}_")

# Leadwin 等账号：{域名}_{广告位类型} (广告单元ID)，如 food.fanquer.com_anchor (23355591177) → food.fanquer.com
GAM_AD_UNIT_DOMAIN_LEAF_PATTERN = re.compile(
    r"([\w][\w.-]*\.\w{2,})_[a-zA-Z][\w]*\s*\(\d+\)",
    re.IGNORECASE,
)

# SITE_NAME 无效时回退到广告单元解析
GAM_INVALID_SITE_NAMES = frozenset({"(unknown)", "unknown"})

# 报表定义：key 用于文件名与环境变量 GAM_REPORTS 筛选
GAM_REPORT_SPECS: list[dict] = [
    {
        "key": "ad_unit",
        "label": "广告单元",
        "dimensions": ["DATE", "AD_UNIT_NAME"],
        "ad_unit_view": "FLAT",
        "columns": GAM_FULL_COLUMNS,
        "includes_product_name": True,
    },
    {
        "key": "country",
        "label": "国家+广告单元",
        "dimensions": ["DATE", "COUNTRY_CODE", "AD_UNIT_NAME"],
        "ad_unit_view": "FLAT",
        "columns": GAM_FULL_COLUMNS,
        "includes_product_name": True,
    },
    {
        "key": "site",
        "label": "站点+广告单元",
        "dimensions": ["DATE", "SITE_NAME", "AD_UNIT_NAME"],
        "ad_unit_view": "FLAT",
        "columns": GAM_SITE_COLUMNS,
        "includes_product_name": True,
    },
    {
        "key": "daily",
        "label": "按日汇总",
        "dimensions": ["DATE"],
        "ad_unit_view": None,
        "columns": GAM_FULL_COLUMNS,
        "includes_product_name": False,
    },
]


# ---------------------------------------------------------------------------
# 配置读取
# ---------------------------------------------------------------------------

def _resolve_credentials_path(raw: str | Path) -> Path:
    """将相对路径解析为基于项目根目录的绝对路径。"""
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _network_code_from_credentials_path(credentials_path: Path) -> str:
    """
    从密钥文件名解析 GAM network_code。

    约定命名：``secrets/gam-23347342743.json`` → ``23347342743``
    """
    match = GAM_CREDENTIALS_FILENAME_PATTERN.match(credentials_path.name)
    if not match:
        raise ValueError(
            "无法从密钥文件名解析 network_code，请使用 gam-{network_code}.json 命名: "
            f"{credentials_path}"
        )
    return match.group(1)


def _lookup_default_gam_account(credentials_path: Path) -> dict[str, str] | None:
    """按密钥路径匹配 DEFAULT_GAM_ACCOUNTS 中的内置账号。"""
    target = credentials_path.resolve()
    for account in DEFAULT_GAM_ACCOUNTS:
        if _resolve_credentials_path(account["credentials_json"]).resolve() == target:
            return account
    return None


def _application_name_from_credentials_file(credentials_path: Path) -> str:
    """读取密钥 JSON 内可选的 application_name 自定义字段。"""
    if not credentials_path.is_file():
        return ""
    try:
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    for key in GAM_CREDENTIALS_APP_NAME_KEYS:
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def _resolve_application_name(credentials_path: Path, network_code: str) -> str:
    """
    解析 GAM application_name。

    优先级：DEFAULT_GAM_ACCOUNTS 匹配项 → 密钥 JSON 可选字段 → network_code。
    """
    matched = _lookup_default_gam_account(credentials_path)
    if matched:
        value = str(matched.get("application_name") or "").strip()
        if value:
            return value
    from_file = _application_name_from_credentials_file(credentials_path)
    if from_file:
        return from_file
    return network_code


def _coerce_report_keys_input(keys) -> list:
    """
    将 report_keys 转为可迭代的字符串列表。

    配置被误写成数字（如 network_code）时抛出明确 ValueError，避免 TypeError。
    """
    if keys is None:
        return []
    if isinstance(keys, (int, float)):
        raise ValueError(
            f"report_keys 必须是字符串数组，不能是数字（疑似误填了 network_code）: {keys!r}"
        )
    if isinstance(keys, str):
        text = keys.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"report_keys JSON 解析失败: {exc}") from exc
            if not isinstance(parsed, list):
                raise ValueError("report_keys JSON 必须是字符串数组")
            return parsed
        return [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(keys, (list, tuple, set, frozenset)):
        return list(keys)
    raise ValueError(
        f"report_keys 格式无效，期望字符串数组，实际为 {type(keys).__name__}: {keys!r}"
    )


def _coerce_str_list(values, *, field_name: str) -> list[str]:
    """将白名单等字段安全转为字符串列表。"""
    if values is None:
        return []
    if isinstance(values, (int, float)):
        raise ValueError(
            f"{field_name} 必须是字符串数组，不能是数字: {values!r}"
        )
    if isinstance(values, str):
        return [values] if values.strip() else []
    if isinstance(values, (list, tuple, set, frozenset)):
        return [str(item) for item in values]
    raise ValueError(
        f"{field_name} 格式无效，期望字符串数组，实际为 {type(values).__name__}: {values!r}"
    )


def _normalize_account_report_keys(keys: list[str] | str | None) -> list[str]:
    """规范化单账号报表类型列表。"""
    if keys is None:
        return list(GAM_SCHEDULER_REPORT_KEYS)
    coerced = _coerce_report_keys_input(keys)
    known = {spec["key"] for spec in GAM_REPORT_SPECS}
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in coerced:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        if key not in known:
            raise ValueError(f"未知报表类型: {key}，可选: {sorted(known)}")
        seen.add(key)
        normalized.append(key)
    if not normalized:
        raise ValueError("至少选择一种报表类型")
    return normalized


def _normalize_gam_account(raw: dict, *, index: int) -> dict:
    """校验并规范化单个 GAM 账号配置。"""
    credentials_raw = (
            raw.get("credentials_json")
            or raw.get("credentials_path")
            or raw.get("credentials")
            or ""
    )
    if not credentials_raw:
        raise ValueError(f"GAM 账号配置第 {index + 1} 项缺少 credentials_json")

    credentials_path = _resolve_credentials_path(credentials_raw)
    network_code = str(raw.get("network_code") or raw.get("networkCode") or "").strip()
    if not network_code:
        network_code = _network_code_from_credentials_path(credentials_path)

    application_name = str(raw.get("application_name") or raw.get("applicationName") or "").strip()
    if not application_name:
        application_name = _resolve_application_name(credentials_path, network_code)

    key = str(raw.get("key") or network_code).strip()
    if "product_whitelist" in raw or "product_names" in raw:
        whitelist_raw = (
            raw["product_whitelist"]
            if "product_whitelist" in raw
            else raw["product_names"]
        )
        product_whitelist = _parse_product_whitelist(whitelist_raw)
    else:
        matched = _lookup_default_gam_account(credentials_path)
        product_whitelist = _parse_product_whitelist(
            matched.get("product_whitelist") if matched else None
        )
    report_keys = _normalize_account_report_keys(raw.get("report_keys"))
    return {
        "key": key,
        "credentials_path": credentials_path,
        "application_name": application_name,
        "network_code": network_code,
        "product_whitelist": sorted(product_whitelist),
        "report_keys": report_keys,
    }


def _parse_gam_accounts_env() -> list[dict] | None:
    """解析 GAM_ACCOUNTS JSON；未设置时返回 None。"""
    raw = os.getenv("GAM_ACCOUNTS", "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"GAM_ACCOUNTS JSON 解析失败: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("GAM_ACCOUNTS 必须是非空 JSON 数组")
    return [_normalize_gam_account(item, index=index) for index, item in enumerate(parsed)]


def _single_account_from_env() -> dict | None:
    """
    单账号模式：仅当显式设置了 GAM_NETWORK_CODE / GAM_CREDENTIALS_JSON /
    GAM_APPLICATION_NAME 之一时启用。
    """
    if not any(
        os.getenv(name)
        for name in ("GAM_NETWORK_CODE", "GAM_CREDENTIALS_JSON", "GAM_APPLICATION_NAME")
    ):
        return None
    single_raw: dict = {
        "credentials_json": os.getenv("GAM_CREDENTIALS_JSON", str(DEFAULT_CREDENTIALS)),
        "application_name": os.getenv("GAM_APPLICATION_NAME", ""),
        "network_code": os.getenv("GAM_NETWORK_CODE", ""),
    }
    if os.getenv("GAM_PRODUCT_WHITELIST"):
        single_raw["product_whitelist"] = os.getenv("GAM_PRODUCT_WHITELIST", "")
    return _normalize_gam_account(single_raw, index=0)


def _default_gam_accounts() -> list[dict]:
    """加载内置默认多账号列表。"""
    return [
        _normalize_gam_account(account, index=index)
        for index, account in enumerate(DEFAULT_GAM_ACCOUNTS)
    ]


def _filter_gam_accounts(accounts: list[dict]) -> list[dict]:
    """按 GAM_ACCOUNT 环境变量筛选账号（匹配 key 或 network_code）。"""
    raw = os.getenv("GAM_ACCOUNT", "").strip()
    if not raw:
        return accounts
    tokens = {part.strip().lower() for part in raw.split(",") if part.strip()}
    filtered = [
        account
        for account in accounts
        if account["key"].lower() in tokens or account["network_code"] in tokens
    ]
    if not filtered:
        available = ", ".join(f"{a['key']}({a['network_code']})" for a in accounts)
        raise ValueError(f"GAM_ACCOUNT 未匹配任何账号: {raw}，可选: {available}")
    return filtered


def _resolve_gam_accounts() -> list[dict]:
    """返回待拉取的 GAM 账号列表（已按 GAM_ACCOUNT 筛选）。"""
    parsed = _parse_gam_accounts_env()
    if parsed is not None:
        accounts = parsed
    else:
        single = _single_account_from_env()
        accounts = [single] if single else _default_gam_accounts()
    return _filter_gam_accounts(accounts)


def _gam_run_config() -> dict:
    """
    汇总与账号无关的运行配置：日期范围、输出目录、报表类型、API 版本。

    Returns:
        包含 start_date、end_date、output_dir、report_keys、api_version 的字典。
    """
    start_date = _parse_date_env("GAM_START_DATE") or (date.today() - timedelta(days=1))
    end_date = _parse_date_env("GAM_END_DATE") or start_date

    if end_date < start_date:
        raise ValueError(f"GAM_END_DATE ({end_date}) 不能早于 GAM_START_DATE ({start_date})")

    output_dir = Path(os.getenv("GAM_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
    report_keys = _parse_report_keys_env()

    return {
        "api_version": os.getenv("GAM_API_VERSION", DEFAULT_API_VERSION),
        "start_date": start_date,
        "end_date": end_date,
        "output_dir": output_dir,
        "report_keys": report_keys,
    }


def _merge_account_config(run_cfg: dict, account: dict) -> dict:
    """合并账号配置与运行配置，供拉数与写文件使用。"""
    return {
        **run_cfg,
        "account_key": account["key"],
        "credentials_path": account["credentials_path"],
        "application_name": account["application_name"],
        "network_code": str(account["network_code"]),
        "product_whitelist": _coerce_str_list(
            account.get("product_whitelist"),
            field_name="product_whitelist",
        ),
    }


def _gam_config() -> dict:
    """
    返回第一个可用账号的完整配置（兼容单账号测试与旧调用）。

    多账号拉数请使用 _gam_run_config() + _resolve_gam_accounts()。
    """
    run_cfg = _gam_run_config()
    accounts = _resolve_gam_accounts()
    return _merge_account_config(run_cfg, accounts[0])


def _parse_report_keys_env() -> list[str]:
    """解析 GAM_REPORTS；未设置则拉取全部报表类型。"""
    raw = os.getenv("GAM_REPORTS", "").strip()
    if not raw:
        return [spec["key"] for spec in GAM_REPORT_SPECS]
    keys = [part.strip() for part in raw.split(",") if part.strip()]
    known = {spec["key"] for spec in GAM_REPORT_SPECS}
    unknown = [key for key in keys if key not in known]
    if unknown:
        raise ValueError(f"未知 GAM_REPORTS 键: {unknown}，可选: {sorted(known)}")
    return keys


def _resolve_report_specs(report_keys: list[str]) -> list[dict]:
    """按配置键顺序返回待拉取的报表定义。"""
    by_key = {spec["key"]: spec for spec in GAM_REPORT_SPECS}
    return [by_key[key] for key in report_keys]


def _parse_date_env(name: str) -> date | None:
    """解析环境变量中的 ISO 日期（YYYY-MM-DD），未设置则返回 None。"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return date.fromisoformat(raw)


def _date_to_api_dict(value: date) -> dict[str, int]:
    """
    将 Python date 转为 GAM API 要求的日期结构。

    GAM ReportQuery 的 startDate/endDate 格式为：
    {"year": 2026, "month": 6, "day": 30}
    """
    return {"year": value.year, "month": value.month, "day": value.day}


def _credentials_available(cfg: dict) -> bool:
    """检查服务账号 JSON 文件是否存在。"""
    return cfg["credentials_path"].is_file()


def _require_googleads() -> None:
    """延迟导入 googleads；未安装时抛出明确错误提示 pip install googleads。"""
    try:
        from googleads import ad_manager, oauth2  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("未安装 googleads，请执行: pip install googleads") from exc


# ---------------------------------------------------------------------------
# GAM 客户端与报表
# ---------------------------------------------------------------------------

def _build_ad_manager_client(cfg: dict):
    """
    使用服务账号 JSON 构建 AdManagerClient。

    流程：
    1. GoogleServiceAccountClient 用私钥换取 OAuth2 access token
    2. AdManagerClient 绑定 application_name 与 network_code，后续所有 API 针对该网络

    Args:
        cfg: _gam_config() 返回的配置字典

    Returns:
        googleads.ad_manager.AdManagerClient 实例
    """
    _require_googleads()
    from googleads import ad_manager, oauth2

    oauth2_client = oauth2.GoogleServiceAccountClient(
        str(cfg["credentials_path"]),
        oauth2.GetAPIScope("ad_manager"),  # scope: https://www.googleapis.com/auth/dfp
    )
    return ad_manager.AdManagerClient(
        oauth2_client,
        cfg["application_name"],
        network_code=cfg["network_code"],
    )


def _build_report_job(
        *,
        dimensions: list[str],
        start_date: date,
        end_date: date,
        columns: list[str] | None = None,
        ad_unit_view: str | None = "FLAT",
) -> dict:
    """
    构建 ReportService.runReportJob 所需的报表任务字典。

    Args:
        dimensions: 报表维度，如 DATE、AD_UNIT_NAME、COUNTRY_CODE
        start_date: 开始日期（含）
        end_date: 结束日期（含）
        columns: 指标列；默认 GAM_FULL_COLUMNS
        ad_unit_view: 含广告单元维度时为 FLAT/HIERARCHICAL；无广告单元维度时传 None
    """
    report_query: dict = {
        "dimensions": dimensions,
        "columns": columns or GAM_FULL_COLUMNS,
        "dateRangeType": "CUSTOM_DATE",
        "startDate": _date_to_api_dict(start_date),
        "endDate": _date_to_api_dict(end_date),
    }
    if ad_unit_view and any(dim.startswith("AD_UNIT") for dim in dimensions):
        report_query["adUnitView"] = ad_unit_view
    return {"reportQuery": report_query}


def _validate_report_spec_shape(spec: dict) -> None:
    """校验报表定义中的 dimensions / columns 必须为列表。"""
    dimensions = spec.get("dimensions")
    if not isinstance(dimensions, (list, tuple)):
        raise ValueError(
            f"报表 {spec.get('key', '?')} 的 dimensions 配置无效: {dimensions!r}"
        )
    columns = spec.get("columns", GAM_FULL_COLUMNS)
    if columns is not None and not isinstance(columns, (list, tuple)):
        raise ValueError(
            f"报表 {spec.get('key', '?')} 的 columns 配置无效: {columns!r}"
        )


def _build_report_job_from_spec(spec: dict, start_date: date, end_date: date) -> dict:
    """根据 GAM_REPORT_SPECS 条目构建报表任务。"""
    _validate_report_spec_shape(spec)
    return _build_report_job(
        dimensions=list(spec["dimensions"]),
        start_date=start_date,
        end_date=end_date,
        columns=list(spec.get("columns", GAM_FULL_COLUMNS)),
        ad_unit_view=spec.get("ad_unit_view"),
    )


def _build_sample_report_job(start_date: date, end_date: date) -> dict:
    """兼容旧调用：拉取广告单元全量指标报表。"""
    return _build_report_job_from_spec(
        next(spec for spec in GAM_REPORT_SPECS if spec["key"] == "ad_unit"),
        start_date,
        end_date,
    )


def _download_report_csv_bytes(client, report_job: dict, *, api_version: str) -> bytes:
    """
    提交报表任务、轮询直至完成，并下载原始 CSV 字节流。

    GAM 报表为异步：runReportJob → 轮询 getReportJobStatus → getReportDownloadUrlWithOptions。

    Args:
        client: AdManagerClient
        report_job: _build_sample_report_job 返回的字典
        api_version: API 版本字符串，如 v202605

    Returns:
        UTF-8 编码的 CSV 文件完整内容（bytes）
    """
    report_downloader = client.GetDataDownloader(version=api_version)

    # WaitForReport 内部会阻塞轮询，默认每 30 秒查一次状态，直至 COMPLETED 或 FAILED
    report_job_id = report_downloader.WaitForReport(report_job)

    buffer = io.BytesIO()
    report_downloader.DownloadReportToFile(
        report_job_id,
        "CSV_DUMP",  # 导出格式：逗号分隔，字段名带 Dimension./Column. 前缀
        buffer,
        include_totals_row=False,  # 不含汇总行，便于按行入库
        use_gzip_compression=False,  # 不 gzip，直接写入 BytesIO 便于解码
    )
    return buffer.getvalue()


def _metric_column_to_field(column_name: str) -> str:
    """GAM 指标列名转 snake_case 平台字段，如 TOTAL_AD_REQUESTS → total_ad_requests。"""
    return column_name.removeprefix("Column.").lower()


def _is_revenue_metric(column_name: str) -> bool:
    name = column_name.removeprefix("Column.")
    return "REVENUE" in name or name.endswith("CPM_AND_CPC_REVENUE")


def _is_rate_metric(column_name: str) -> bool:
    return column_name.removeprefix("Column.").endswith("_RATE")


def _parse_gam_metric_value(column_name: str, raw: str) -> int | float:
    """解析 GAM 指标原始字符串；收入列 ÷1_000_000，比率列统一为百分比。"""
    text = (raw or "0").strip()
    if _is_revenue_metric(column_name):
        return int(text or 0) / GAM_REVENUE_MICRO_DIVISOR
    if _is_rate_metric(column_name):
        value = float(text or 0)
        # GAM 可能返回 0.82（比例）或 82（百分比），统一为百分比
        if 0 < value <= 1:
            value *= 100
        return round(value, 4)
    return int(text or 0)


def _spec_dimension_fields(spec: dict) -> list[tuple[str, str]]:
    """返回报表维度 (GAM键, 平台字段名) 列表，含自动附带的 AD_UNIT_ID。"""
    pairs: list[tuple[str, str]] = []
    for dim in spec["dimensions"]:
        gam_key = f"Dimension.{dim}"
        platform_key = GAM_DIMENSION_MAPPING.get(gam_key)
        if platform_key:
            pairs.append((gam_key, platform_key))
    if any(name.startswith("AD_UNIT") for name in spec["dimensions"]):
        pairs.append(("Dimension.AD_UNIT_ID", "ad_unit_id"))
    return pairs


def _spec_metric_columns(spec: dict) -> list[str]:
    return list(spec.get("columns", GAM_FULL_COLUMNS))


def _is_leaf_ad_unit(ad_unit: str) -> bool:
    text = ad_unit or ""
    return bool(
        GAM_AD_UNIT_LEAF_PATTERN.search(text)
        or GAM_AD_UNIT_DOMAIN_LEAF_PATTERN.search(text)
    )


def _spec_includes_product_name(spec: dict) -> bool:
    """报表是否输出 product_name 列（可识别/解析产品名时）。"""
    if "includes_product_name" in spec:
        return bool(spec["includes_product_name"])
    return spec.get("key", "") in GAM_REPORT_KEYS_WITH_PRODUCT_NAME


def _spec_has_ad_unit_dimension(spec: dict) -> bool:
    return any(name.startswith("AD_UNIT") for name in spec.get("dimensions", []))


def _product_context_from_row(row: dict[str, str], spec: dict) -> dict:
    """从原始行提取解析 product_name 所需的维度上下文。"""
    context: dict[str, str] = {}
    for gam_key, platform_key in _spec_dimension_fields(spec):
        context[platform_key] = row.get(gam_key, "")
    return context


def _enrich_rows_with_product_name(
        rows: list[dict[str, str]],
        spec: dict,
) -> list[dict[str, str]]:
    """为支持产品名解析的报表原始行追加 product_name 列。"""
    if not _spec_includes_product_name(spec):
        return rows
    enriched: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        item["product_name"] = _resolve_product_name(_product_context_from_row(row, spec))
        enriched.append(item)
    return enriched


def _expected_output_field_keys(spec: dict) -> list[str]:
    """CSV/JSON 输出列（GAM 原始列 + 可选 product_name）。"""
    field_keys = _expected_field_keys(spec)
    if _spec_includes_product_name(spec):
        field_keys = [*field_keys, "product_name"]
    return field_keys


def _expected_mapped_meta_fields(spec: dict) -> list[str]:
    """mapped 行中的元数据字段。"""
    meta = ["network_code", "report_key"]
    if _spec_includes_product_name(spec):
        meta.append("product_name")
    if _spec_has_ad_unit_dimension(spec):
        meta.append("is_leaf_ad_unit")
    return meta


def _expected_field_keys(spec: dict) -> list[str]:
    """生成报表应有的全部字段键（含 GAM 自动附带的 AD_UNIT_ID）。"""
    dim_keys = [f"Dimension.{name}" for name in spec["dimensions"]]
    if any(name.startswith("AD_UNIT") for name in spec["dimensions"]):
        dim_keys.append("Dimension.AD_UNIT_ID")
    metric_keys = [f"Column.{name}" for name in spec.get("columns", GAM_FULL_COLUMNS)]
    return dim_keys + metric_keys


def _normalize_report_rows(
        rows: list[dict[str, str]],
        spec: dict,
) -> list[dict[str, str]]:
    """
    补齐 GAM CSV 省略的全零列，保证每行列数与请求指标一致。

    GAM 导出时会丢弃整列均为 0 的指标（如 TOTAL_INVENTORY_LEVEL_*），
    入库或对比前需统一补为 \"0\"。
    """
    if not rows:
        return rows
    field_order = _expected_field_keys(spec)
    normalized: list[dict[str, str]] = []
    for row in rows:
        item: dict[str, str] = {}
        for key in field_order:
            if key.startswith("Dimension."):
                item[key] = row.get(key, "")
            else:
                item[key] = row.get(key, "0")
        # 保留 GAM 额外返回列，避免丢列
        for key, value in row.items():
            if key not in item and value is not None:
                item[key] = value
        normalized.append(item)
    return normalized


def _validate_report_rows_completeness(
        rows: list[dict[str, str]],
        business_rows: list[dict],
        spec: dict,
) -> dict:
    """校验行数与列是否完整，返回摘要供 manifest 记录。"""
    field_order = _expected_output_field_keys(spec)
    dim_fields = [platform for _, platform in _spec_dimension_fields(spec)]
    metric_fields = [_metric_column_to_field(f"Column.{name}") for name in _spec_metric_columns(spec)]
    platform_aliases = list(GAM_PLATFORM_METRIC_ALIASES.keys())
    derived_fields = list(GAM_DERIVED_METRIC_FORMULAS.keys())
    meta_fields = _expected_mapped_meta_fields(spec)
    expected_mapped_keys = set(
        dim_fields + metric_fields + platform_aliases + derived_fields + meta_fields
    )

    incomplete_rows = 0
    for row in rows:
        if any(key not in row for key in field_order):
            incomplete_rows += 1

    incomplete_mapped = 0
    for item in business_rows:
        if any(key not in item for key in expected_mapped_keys):
            incomplete_mapped += 1

    return {
        "raw_row_count": len(rows),
        "mapped_row_count": len(business_rows),
        "row_count_match": len(rows) == len(business_rows),
        "expected_raw_columns": len(field_order),
        "expected_mapped_columns": len(expected_mapped_keys),
        "incomplete_raw_rows": incomplete_rows,
        "incomplete_mapped_rows": incomplete_mapped,
        "columns_complete": incomplete_rows == 0 and incomplete_mapped == 0,
    }


def _rows_to_csv_bytes(rows: list[dict[str, str]], fieldnames: list[str]) -> bytes:
    """将补齐后的行列表写回 CSV 字节流。"""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _calculate_derived_metrics(item: dict) -> dict:
    """
    按平台公式计算衍生比率指标（与 AdData.calculate_rates / excel calculate_rates 一致）。

    - coverage_rate = 匹配数 / 请求数 × 100
    - display_rate  = 展示数 / 匹配数 × 100
    - click_rate    = 点击数 / 展示数 × 100
    - ecpm_before_deduct = 收益 / 展示数 × 1000
    - cpc           = 收益 / 点击数
    """
    request_count = int(item.get("request_count", 0) or 0)
    match_count = int(item.get("match_count", 0) or 0)
    display_count = int(item.get("display_count", 0) or 0)
    click_count = int(item.get("click_count", 0) or 0)
    revenue = float(item.get("revenue_before_deduct", 0) or 0)

    item["coverage_rate"] = round(
        (match_count / request_count * 100) if request_count > 0 else 0.0,
        2,
    )
    item["display_rate"] = round(
        (display_count / match_count * 100) if match_count > 0 else 0.0,
        2,
    )
    item["click_rate"] = round(
        (click_count / display_count * 100) if display_count > 0 else 0.0,
        2,
    )
    item["ecpm_before_deduct"] = round(
        (revenue / display_count * 1000) if display_count > 0 else 0.0,
        2,
    )
    item["cpc"] = round(
        (revenue / click_count) if click_count > 0 else 0.0,
        4,
    )
    return item


def _extract_product_name_from_ad_unit(ad_unit: str) -> str:
    """
    从 GAM 广告单元层级路径提取产品名，作为平台 product_name。

    支持两种叶子单元命名：

    1. ``ume_{产品名}_{YYYYMMDD}_{类型}_{序号}`` / ``cy_...``
       例：``ume_buildascamempire.com_20260608_banner_1`` → ``buildascamempire.com``

    2. ``{域名}_{广告位类型} (广告单元ID)``
       例：``food.fanquer.com_anchor (23355591177)`` → ``food.fanquer.com``

    父级单元（无上述叶子形态）无法对应单一产品，返回空字符串。
    """
    if not ad_unit:
        return ""

    match = GAM_AD_UNIT_LEAF_PATTERN.search(ad_unit)
    if match:
        return match.group(1)
    match = GAM_AD_UNIT_DOMAIN_LEAF_PATTERN.search(ad_unit)
    if match:
        return match.group(1)
    return ""


def _resolve_product_name(item: dict) -> str:
    """按报表可用维度解析产品名称（有效站点名优先，否则从广告单元路径提取）。"""
    site_name = (item.get("site_name") or "").strip()
    if site_name and site_name.lower() not in GAM_INVALID_SITE_NAMES:
        return site_name
    return _extract_product_name_from_ad_unit(item.get("ad_unit", ""))


def _normalize_product_whitelist_name(name: str) -> str:
    """白名单匹配用：去首尾空白、转小写，并去掉 www. 前缀。"""
    normalized = str(name).strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def _parse_product_whitelist(raw) -> frozenset[str]:
    """
    解析产品白名单。

    支持 list、逗号分隔字符串、JSON 数组字符串；空表示不过滤（全量）。
    """
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return frozenset()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"product_whitelist JSON 解析失败: {exc}") from exc
            if not isinstance(parsed, list):
                raise ValueError("product_whitelist JSON 必须是字符串数组")
            raw = parsed
        else:
            raw = [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(raw, (list, tuple, set, frozenset)):
        names = {
            _normalize_product_whitelist_name(str(item))
            for item in raw
            if str(item).strip()
        }
        return frozenset(names)
    raise ValueError(f"product_whitelist 格式无效: {raw!r}")


def _account_product_whitelist_set(account_or_cfg: dict) -> frozenset[str]:
    """从账号或合并后的 cfg 读取白名单集合。"""
    return _parse_product_whitelist(account_or_cfg.get("product_whitelist"))


def _row_is_leaf_for_spec(row: dict, spec: dict) -> bool:
    """无广告单元维度的报表视为叶子行；否则按广告单元路径判断。"""
    if not _spec_has_ad_unit_dimension(spec):
        return True
    return _is_leaf_ad_unit(str(row.get("Dimension.AD_UNIT_NAME") or ""))


def _row_whitelist_product_name(row: dict, spec: dict) -> str:
    """
    白名单匹配用产品名。

    有广告单元维度时优先用单元名解析结果，避免 site 报表因 SITE_NAME 与单元名不一致而误入。
    """
    if _spec_has_ad_unit_dimension(spec):
        ad_unit_name = str(
            row.get("Dimension.AD_UNIT_NAME") or row.get("ad_unit") or ""
        )
        from_ad_unit = _extract_product_name_from_ad_unit(ad_unit_name)
        if from_ad_unit:
            return _normalize_product_whitelist_name(from_ad_unit)
    return _normalize_product_whitelist_name(row.get("product_name") or "")


def _filter_rows_by_product_whitelist(
    rows: list[dict],
    whitelist: frozenset[str],
    *,
    spec: dict,
) -> tuple[list[dict], dict]:
    """
    按 product_name 白名单过滤行。

    白名单非空时同时要求叶子广告单元（避免父级行带站点名误入）。
    白名单为空或报表不含 product_name 时原样返回。
    """
    stats = {
        "applied": False,
        "rows_before": len(rows),
        "rows_after": len(rows),
        "whitelist_size": len(whitelist),
        "dropped_non_leaf": 0,
        "whitelist_not_found": [],
    }
    if not whitelist or not _spec_includes_product_name(spec):
        return rows, stats

    filtered: list[dict] = []
    dropped_non_leaf = 0
    matched_names: set[str] = set()
    for row in rows:
        product_name = _row_whitelist_product_name(row, spec)
        if product_name not in whitelist:
            continue
        if not _row_is_leaf_for_spec(row, spec):
            dropped_non_leaf += 1
            continue
        matched_names.add(product_name)
        filtered.append(row)

    stats["applied"] = True
    stats["rows_after"] = len(filtered)
    stats["dropped_non_leaf"] = dropped_non_leaf
    stats["whitelist_not_found"] = sorted(whitelist - matched_names)
    return filtered, stats


def _skipped_report_summary(cfg: dict, spec: dict, *, reason: str) -> dict:
    """白名单启用时跳过无产品维度报表的摘要。"""
    fieldnames = _expected_output_field_keys(spec)
    return {
        "report_key": spec["key"],
        "label": spec["label"],
        "dimensions": spec["dimensions"],
        "metrics": spec.get("columns", GAM_FULL_COLUMNS),
        "business_field_mapping": {
            gam_key: {"field": field, "label": label}
            for gam_key, (field, label) in GAM_BUSINESS_METRIC_MAPPING.items()
        },
        "row_count": 0,
        "columns": fieldnames,
        "completeness": {"skipped": True, "reason": reason},
        "skipped": True,
        "skip_reason": reason,
        "product_filter": {
            "applied": False,
            "rows_before": 0,
            "rows_after": 0,
            "whitelist_size": len(_account_product_whitelist_set(cfg)),
        },
        "paths": {},
        "sample_row": None,
        "sample_business_row": None,
    }


def _rows_to_business_rows(
        rows: list[dict[str, str]],
        spec: dict,
        *,
        network_code: str = "",
        report_key: str = "",
) -> list[dict]:
    """
    将 GAM 原始行映射为全量业务字段（行、列均完整）。

    每行包含：
    - 报表全部维度（无值时为空字符串）
    - 报表全部指标（snake_case，收入已 ÷1_000_000）
    - 平台别名（request_count / match_count / …）
    - 衍生比率指标
    - product_name（可解析报表必有，无则空字符串）、is_leaf_ad_unit、network_code、report_key
    """
    dim_fields = _spec_dimension_fields(spec)
    metric_columns = _spec_metric_columns(spec)
    includes_product_name = _spec_includes_product_name(spec)
    has_ad_unit = _spec_has_ad_unit_dimension(spec)
    business_rows: list[dict] = []

    for row in rows:
        item: dict = {
            "network_code": network_code,
            "report_key": report_key,
        }
        if includes_product_name:
            item["product_name"] = ""
        if has_ad_unit:
            item["is_leaf_ad_unit"] = False

        for gam_key, platform_key in dim_fields:
            item[platform_key] = row.get(gam_key, "")

        if includes_product_name:
            item["product_name"] = row.get("product_name") or _resolve_product_name(item)
        if has_ad_unit:
            item["is_leaf_ad_unit"] = _is_leaf_ad_unit(str(item.get("ad_unit") or ""))

        for column_name in metric_columns:
            gam_key = f"Column.{column_name}"
            field_name = _metric_column_to_field(gam_key)
            item[field_name] = _parse_gam_metric_value(gam_key, row.get(gam_key, "0"))

        for alias, source_field in GAM_PLATFORM_METRIC_ALIASES.items():
            item[alias] = item.get(source_field, 0)

        item = _calculate_derived_metrics(item)
        business_rows.append(item)

    return business_rows


def _parse_csv_bytes(data: bytes) -> list[dict[str, str]]:
    """
    将 CSV 字节流解析为字典列表，每行一个 dict，键为 CSV 表头。

    示例键名：
    - Dimension.DATE
    - Dimension.AD_UNIT_NAME
    - Column.TOTAL_LINE_ITEM_LEVEL_IMPRESSIONS
    """
    text = data.decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def _run_report_job(client, report_job: dict, *, api_version: str) -> list[dict[str, str]]:
    """下载报表并解析为行列表（供测试或仅需内存数据的场景）。"""
    return _parse_csv_bytes(_download_report_csv_bytes(client, report_job, api_version=api_version))


# ---------------------------------------------------------------------------
# 本地文件保存
# ---------------------------------------------------------------------------

def _date_label(start_date: date, end_date: date) -> str:
    """生成文件名中的日期段标签。"""
    if start_date == end_date:
        return start_date.isoformat()
    return f"{start_date.isoformat()}_{end_date.isoformat()}"


def _build_output_paths(
        cfg: dict,
        report_key: str,
        *,
        stamp: str | None = None,
) -> dict[str, Path]:
    """
    根据日期范围、报表键与批次时间戳生成输出文件路径（尚未写入磁盘）。

    命名规则：
    - gam_23347342743_ad_unit_2026-06-30_20260701_154835.csv
    - gam_23348711678_country_2026-06-01_2026-06-30_20260701_154835.csv
    """
    cfg["output_dir"].mkdir(parents=True, exist_ok=True)
    run_stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    date_label = _date_label(cfg["start_date"], cfg["end_date"])
    base = cfg["output_dir"] / f"gam_{cfg['network_code']}_{report_key}_{date_label}_{run_stamp}"
    return {
        "csv": base.with_suffix(".csv"),
        "json": base.with_suffix(".json"),
        "mapped_json": base.with_name(f"{base.name}_mapped").with_suffix(".json"),
    }


def _build_manifest_path(cfg: dict, *, stamp: str) -> Path:
    """同批次 manifest 文件路径。"""
    date_label = _date_label(cfg["start_date"], cfg["end_date"])
    return cfg["output_dir"] / f"gam_manifest_{cfg['network_code']}_{date_label}_{stamp}.json"


def save_report_data(
        rows: list[dict[str, str]],
        raw_csv: bytes,
        output_paths: dict[str, Path],
        *,
        business_rows: list[dict] | None = None,
) -> dict[str, Path]:
    """
    将完整报表持久化到磁盘。

    - CSV：在 GAM 原始导出基础上补齐全零列后写回，列与 JSON 一致
    - JSON：结构化数组，每行含请求的全部维度与指标列
    - mapped_json：平台业务字段，收益已换算为 USD

    Args:
        rows: 解析后的全部数据行
        raw_csv: 未解析的 CSV 原始内容
        output_paths: _build_output_paths 返回的路径字典
        business_rows: 业务字段映射后的行列表

    Returns:
        实际写入的文件路径字典（与 output_paths 相同）
    """
    output_paths["csv"].write_bytes(raw_csv)
    output_paths["json"].write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if business_rows is not None and "mapped_json" in output_paths:
        output_paths["mapped_json"].write_text(
            json.dumps(business_rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return output_paths


def fetch_report_rows(
    client,
    cfg: dict,
    spec: dict,
) -> dict:
    """
    拉取单份报表到内存（不写文件）。

    Returns:
        含 business_rows、product_filter、skipped 等字段的摘要字典
    """
    whitelist = _account_product_whitelist_set(cfg)
    if whitelist and not _spec_includes_product_name(spec):
        skipped = _skipped_report_summary(
            cfg,
            spec,
            reason="账号配置了 product_whitelist，daily 报表无产品维度已跳过",
        )
        skipped["business_rows"] = []
        return skipped

    report_job = _build_report_job_from_spec(spec, cfg["start_date"], cfg["end_date"])
    raw_csv = _download_report_csv_bytes(client, report_job, api_version=cfg["api_version"])
    rows = _normalize_report_rows(_parse_csv_bytes(raw_csv), spec)
    rows = _enrich_rows_with_product_name(rows, spec)
    rows, product_filter = _filter_rows_by_product_whitelist(rows, whitelist, spec=spec)
    business_rows = _rows_to_business_rows(
        rows,
        spec,
        network_code=cfg["network_code"],
        report_key=spec["key"],
    )
    return {
        "report_key": spec["key"],
        "label": spec["label"],
        "dimensions": spec["dimensions"],
        "row_count": len(business_rows),
        "rows": rows,
        "business_rows": business_rows,
        "product_filter": product_filter,
        "skipped": False,
    }


def fetch_account_reports_to_memory(
    client,
    cfg: dict,
    report_specs: list[dict],
) -> dict:
    """拉取单账号下多份报表到内存。"""
    reports: dict[str, list[dict]] = {}
    summaries: list[dict] = []
    for spec in report_specs:
        summary = fetch_report_rows(client, cfg, spec)
        summaries.append(summary)
        business_rows = summary.get("business_rows")
        if business_rows is None:
            business_rows = []
        elif not isinstance(business_rows, list):
            raise ValueError(
                f"报表 {spec['key']} 的 business_rows 类型无效: {type(business_rows).__name__}"
            )
        reports[spec["key"]] = business_rows

    return {
        "account_key": cfg["account_key"],
        "network_code": cfg["network_code"],
        "application_name": cfg["application_name"],
        "start_date": cfg["start_date"].isoformat(),
        "end_date": cfg["end_date"].isoformat(),
        "reports": reports,
        "report_summaries": summaries,
    }


def run_gam_fetch_to_memory(
    start_date: date,
    end_date: date,
    *,
    report_keys: list[str] | None = None,
    accounts: list[dict] | None = None,
) -> list[dict]:
    """
    多账号 GAM 拉数到内存（定时任务入口）。

    Args:
        start_date: 开始日期（含）
        end_date: 结束日期（含）
        report_keys: 全局默认报表键（账号未配置 report_keys 时使用）
        accounts: 可选账号配置（含 product_whitelist、report_keys）；未传则走环境变量/内置默认

    Returns:
        每个账号一个 bundle dict（含 reports: ad_unit/country/site → list[dict]）
    """
    _require_googleads()
    run_cfg = _gam_run_config()
    run_cfg["start_date"] = start_date
    run_cfg["end_date"] = end_date
    default_keys = report_keys or list(GAM_SCHEDULER_REPORT_KEYS)
    if accounts is not None:
        resolved_accounts = [
            _normalize_gam_account(account, index=index)
            for index, account in enumerate(accounts)
        ]
    else:
        resolved_accounts = _resolve_gam_accounts()
    available_accounts = [
        account for account in resolved_accounts if account["credentials_path"].is_file()
    ]
    if not available_accounts:
        raise RuntimeError("没有可用的 GAM 密钥文件")

    bundles: list[dict] = []
    failures: list[str] = []
    for account in available_accounts:
        cfg = _merge_account_config(run_cfg, account)
        raw_keys = account.get("report_keys")
        account_keys = (
            _normalize_account_report_keys(raw_keys)
            if raw_keys is not None
            else list(default_keys)
        )
        report_specs = _resolve_report_specs(account_keys)
        try:
            client = _build_ad_manager_client(cfg)
            bundles.append(fetch_account_reports_to_memory(client, cfg, report_specs))
        except Exception as exc:
            logger.exception(
                "GAM 账号拉数失败 account=%s network=%s",
                cfg["account_key"],
                cfg["network_code"],
            )
            failures.append(
                f"{cfg['account_key']}({cfg['network_code']}): {type(exc).__name__}: {exc}"
            )
    if failures and not bundles:
        raise RuntimeError("; ".join(failures))
    if failures:
        for account_bundle in bundles:
            account_bundle.setdefault("warnings", []).extend(failures)
    return bundles


def fetch_and_save_report(
        client,
        cfg: dict,
        spec: dict,
        *,
        stamp: str,
) -> dict:
    """
    拉取单份报表并保存 CSV/JSON。

    Returns:
        含 report_key、label、row_count、paths、columns 的摘要字典
    """
    memory = fetch_report_rows(client, cfg, spec)
    if memory.get("skipped"):
        return memory

    fieldnames = _expected_output_field_keys(spec)
    rows = memory["rows"]
    business_rows = memory["business_rows"]
    product_filter = memory["product_filter"]
    completeness = _validate_report_rows_completeness(rows, business_rows, spec)
    normalized_csv = _rows_to_csv_bytes(rows, fieldnames)
    output_paths = save_report_data(
        rows,
        normalized_csv,
        _build_output_paths(cfg, spec["key"], stamp=stamp),
        business_rows=business_rows,
    )
    return {
        "report_key": spec["key"],
        "label": spec["label"],
        "dimensions": spec["dimensions"],
        "metrics": spec.get("columns", GAM_FULL_COLUMNS),
        "business_field_mapping": {
            gam_key: {"field": field, "label": label}
            for gam_key, (field, label) in GAM_BUSINESS_METRIC_MAPPING.items()
        },
        "row_count": len(rows),
        "columns": fieldnames,
        "completeness": completeness,
        "product_filter": product_filter,
        "paths": {
            "csv": str(output_paths["csv"]),
            "json": str(output_paths["json"]),
            "mapped_json": str(output_paths["mapped_json"]),
        },
        "sample_row": rows[0] if rows else None,
        "sample_business_row": business_rows[0] if business_rows else None,
    }


def save_manifest(cfg: dict, *, stamp: str, reports: list[dict]) -> Path:
    """写入同批次 manifest，汇总各报表元数据。"""
    manifest_path = _build_manifest_path(cfg, stamp=stamp)
    payload = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "account_key": cfg.get("account_key"),
        "application_name": cfg["application_name"],
        "network_code": cfg["network_code"],
        "credentials_path": str(cfg["credentials_path"]),
        "api_version": cfg["api_version"],
        "date_range": {
            "start": cfg["start_date"].isoformat(),
            "end": cfg["end_date"].isoformat(),
        },
        "metric_groups": {
            "request": GAM_REQUEST_COLUMNS,
            "site_request": GAM_SITE_REQUEST_COLUMNS,
            "delivery": GAM_DELIVERY_COLUMNS,
            "viewability": GAM_VIEWABILITY_COLUMNS,
        },
        "business_metric_mapping": {
            gam_key: {"field": field, "label": label}
            for gam_key, (field, label) in GAM_BUSINESS_METRIC_MAPPING.items()
        },
        "revenue_divisor": GAM_REVENUE_MICRO_DIVISOR,
        "derived_metric_formulas": {
            field: {"label": label, "formula": formula}
            for field, (label, formula) in GAM_DERIVED_METRIC_FORMULAS.items()
        },
        "unavailable_platform_fields": GAM_UNAVAILABLE_PLATFORM_FIELDS,
        "product_name_sources": GAM_PRODUCT_NAME_SOURCES,
        "product_whitelist": list(cfg.get("product_whitelist") or []),
        "platform_field_mapping": _platform_mapping_for_manifest(),
        "reports": reports,
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path


# ---------------------------------------------------------------------------
# 辅助 API：网络信息、已保存报表
# ---------------------------------------------------------------------------

def _get_current_network(client, api_version: str):
    """
    调用 NetworkService.getCurrentNetwork，验证凭证与 networkCode 是否匹配。

    返回对象常见属性：displayName、networkCode、currencyCode。
    """
    network_service = client.GetService("NetworkService", version=api_version)
    return network_service.getCurrentNetwork()


def _list_saved_queries(client, api_version: str) -> list:
    """
    查询账号下已保存的报表模板（SavedQuery）。

    若返回空列表，说明无法用历史 report_id 拉数，需使用 _build_sample_report_job 手工定义维度/指标。
    """
    from googleads import ad_manager

    report_service = client.GetService("ReportService", version=api_version)
    statement = ad_manager.FilterStatement(limit=20).ToStatement()
    page = report_service.getSavedQueriesByStatement(statement)
    results = getattr(page, "results", None)
    if results is None:
        return []
    if isinstance(results, (list, tuple)):
        return list(results)
    return [results]


def get_gam_report_types_catalog() -> list[dict]:
    """返回内置 GAM 报表类型目录（供管理端多选）。"""
    return [_catalog_item_from_spec(spec) for spec in GAM_REPORT_SPECS]


def _catalog_item_from_spec(spec: dict) -> dict:
    return {
        "key": spec["key"],
        "label": spec["label"],
        "dimensions": list(spec["dimensions"]),
        "includes_product_name": bool(spec.get("includes_product_name")),
    }


def _probe_report_spec_available(
    client,
    spec: dict,
    *,
    api_version: str,
    probe_date: date,
) -> bool:
    """提交单日探针报表，判断该账号是否支持此维度组合。"""
    report_service = client.GetService("ReportService", version=api_version)
    job_body = _build_report_job_from_spec(spec, probe_date, probe_date)
    try:
        report_service.runReportJob(job_body)
        return True
    except Exception as exc:
        logger.debug(
            "GAM 报表探针不可用 key=%s dimensions=%s: %s",
            spec.get("key"),
            spec.get("dimensions"),
            exc,
        )
        return False


def probe_available_report_types_for_client(
    client,
    *,
    api_version: str,
    probe_date: date | None = None,
) -> list[dict]:
    """按账号探测可用的报表类型（各网络支持的维度可能不同）。"""
    target_date = probe_date or (date.today() - timedelta(days=1))
    available: list[dict] = []
    for spec in GAM_REPORT_SPECS:
        if _probe_report_spec_available(
            client,
            spec,
            api_version=api_version,
            probe_date=target_date,
        ):
            available.append(_catalog_item_from_spec(spec))
    return available


def _read_service_account_email(credentials_path: Path) -> str:
    try:
        payload = json.loads(credentials_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return str(payload.get("client_email") or "").strip()
    except Exception:
        pass
    return ""


def format_gam_auth_error(
    exc: Exception,
    *,
    credentials_path: Path | str | None = None,
    account_key: str = "",
) -> ValueError:
    """将 Google OAuth / GAM 认证错误转为可读中文说明。"""
    message = str(exc)
    lowered = message.lower()
    path = Path(credentials_path) if credentials_path else None
    email = _read_service_account_email(path) if path and path.is_file() else ""
    email_hint = f" 服务账号：{email}" if email else ""
    account_hint = f" 账号：{account_key}" if account_key else ""
    path_hint = f" 密钥：{path}" if path else ""

    if "invalid_grant" in lowered and "account not found" in lowered:
        return ValueError(
            "Google 服务账号不存在或密钥已失效（invalid_grant: account not found）。"
            f"{account_hint}{email_hint}{path_hint} "
            "请检查：① GCP 中该服务账号是否仍存在；② 是否使用了已删除/轮换前的旧 JSON；"
            "③ 在 GAM → Admin → Access and authorization → Users 添加该 client_email 后，"
            "从 GCP 重新下载密钥并上传。"
        )
    if "invalid_grant" in lowered:
        return ValueError(
            f"Google 密钥授权失败（invalid_grant）。{account_hint}{email_hint}{path_hint} "
            f"原始信息：{message}"
        )
    if "access_denied" in lowered or "permission_denied" in lowered:
        return ValueError(
            f"GAM API 权限不足。{account_hint}{email_hint} "
            "请确认服务账号已在 GAM 后台授权，且具备报表读取权限。"
        )
    return ValueError(f"GAM API 调用失败。{account_hint}{path_hint} {message}")


def probe_gam_report_types_for_account(raw_account: dict) -> dict:
    """
    使用指定账号探测 GAM API，返回该账号实际可用的报表类型目录。

    各 GAM 网络支持的报表维度可能不同，探针会对每种内置报表尝试提交任务。
    """
    _require_googleads()
    account = _normalize_gam_account(raw_account, index=0)
    credentials_path = account["credentials_path"]
    if not credentials_path.is_file():
        raise FileNotFoundError(f"GAM 密钥文件不存在: {credentials_path}")

    run_cfg = _gam_run_config()
    cfg = _merge_account_config(run_cfg, account)
    try:
        client = _build_ad_manager_client(cfg)
        network = _get_current_network(client, cfg["api_version"])
        saved_queries = _list_saved_queries(client, cfg["api_version"])
        report_types = probe_available_report_types_for_client(
            client,
            api_version=cfg["api_version"],
        )
    except Exception as exc:
        raise format_gam_auth_error(
            exc,
            credentials_path=credentials_path,
            account_key=str(cfg.get("account_key") or account.get("key") or ""),
        ) from exc
    if not report_types:
        raise RuntimeError(
            f"账号 {cfg['account_key']} 未探测到可用报表类型，请检查 GAM 权限与网络配置"
        )
    return {
        "account_key": cfg["account_key"],
        "network_code": str(getattr(network, "networkCode", "")),
        "network_display_name": str(getattr(network, "displayName", "")),
        "api_version": cfg["api_version"],
        "saved_query_count": len(saved_queries),
        "report_types": report_types,
    }

# 命令行入口
# ---------------------------------------------------------------------------

def _run_account_fetch(cfg: dict, report_specs: list[dict], *, run_stamp: str) -> list[dict]:
    """拉取单个账号下的全部报表并写入 manifest。"""
    client = _build_ad_manager_client(cfg)

    print("\n[1/3] 客户端初始化成功，获取 Network 信息...")
    network = _get_current_network(client, cfg["api_version"])
    print(
        f"      当前网络: {getattr(network, 'displayName', '')} "
        f"(code={getattr(network, 'networkCode', '')}, "
        f"currency={getattr(network, 'currencyCode', '')})"
    )

    saved_queries = _list_saved_queries(client, cfg["api_version"])
    if saved_queries:
        print(f"      已保存报表模板: {len(saved_queries)} 个（当前使用手工 ReportQuery）")

    print(f"\n[2/3] 提交 {len(report_specs)} 份报表任务...")
    report_summaries: list[dict] = []
    for index, spec in enumerate(report_specs, start=1):
        print(f"      ({index}/{len(report_specs)}) {spec['label']} [{spec['key']}]...")
        summary = fetch_and_save_report(client, cfg, spec, stamp=run_stamp)
        report_summaries.append(summary)
        if summary.get("skipped"):
            print(f"          已跳过: {summary.get('skip_reason')}")
        else:
            print(f"          行数: {summary['row_count']}")
            product_filter = summary.get("product_filter") or {}
            if product_filter.get("applied"):
                print(
                    f"          白名单过滤: {product_filter['rows_before']} → "
                    f"{product_filter['rows_after']} 行"
                )
                if product_filter.get("dropped_non_leaf"):
                    print(
                        f"          排除非叶子行: {product_filter['dropped_non_leaf']} 行"
                    )
                not_found = product_filter.get("whitelist_not_found") or []
                if not_found:
                    print(f"          白名单未命中产品: {', '.join(not_found)}")
                if product_filter["rows_after"] == 0:
                    print("          [警告] 过滤后无数据，请核对白名单与 GAM 实际产品名")
            print(f"          CSV:  {summary['paths']['csv']}")
            print(f"          JSON: {summary['paths']['json']}")
            print(f"          业务: {summary['paths']['mapped_json']}")
            if summary["sample_row"]:
                print(f"          字段数: {len(summary['columns'])}")
            if summary.get("sample_business_row"):
                print(f"          业务首行: {summary['sample_business_row']}")

    manifest_path = save_manifest(cfg, stamp=run_stamp, reports=report_summaries)

    print(f"\n[3/3] 账号 {cfg['account_key']} 报表下载完成")
    print(f"      Manifest: {manifest_path}")
    for summary in report_summaries:
        print(
            f"      - {summary['label']}: {summary['row_count']} 行 "
            f"({', '.join(summary['dimensions'])})"
        )
        if summary.get("sample_business_row"):
            print(f"        业务首行: {summary['sample_business_row']}")
        elif summary["sample_row"]:
            print(f"        原始首行: {summary['sample_row']}")
    return report_summaries


def main() -> int:
    """
    主流程：按账号依次初始化 → 验证网络 → 拉取多份报表 → 保存文件与 manifest → 打印摘要。

    Returns:
        0 成功，1 失败（密钥缺失、依赖未安装或 API 异常）
    """
    run_cfg = _gam_run_config()
    accounts = _resolve_gam_accounts()
    report_specs = _resolve_report_specs(run_cfg["report_keys"])

    print("=== Google Ad Manager API 全面拉数 ===")
    print(f"账号数量:     {len(accounts)}")
    for account in accounts:
        whitelist = account.get("product_whitelist") or []
        whitelist_label = ", ".join(whitelist) if whitelist else "（全量）"
        print(
            f"  - {account['key']}: network={account['network_code']}, "
            f"app={account['application_name']}, cred={account['credentials_path']}, "
            f"白名单={whitelist_label}"
        )
    print(f"API 版本:     {run_cfg['api_version']}")
    print(f"日期范围:     {run_cfg['start_date']} ~ {run_cfg['end_date']}")
    print(f"输出目录:     {run_cfg['output_dir']}")
    print(f"报表类型:     {', '.join(spec['key'] for spec in report_specs)}")
    print(f"指标列:       全量 {len(GAM_FULL_COLUMNS)} 列；站点 {len(GAM_SITE_COLUMNS)} 列（不含 TOTAL_AD_REQUESTS）")
    print("业务映射:     AD_EXCHANGE_* → request/match/display/click/revenue（收益 ÷1_000_000）")

    available_accounts = [account for account in accounts if account["credentials_path"].is_file()]
    missing_accounts = [account for account in accounts if not account["credentials_path"].is_file()]
    if missing_accounts:
        print("\n[警告] 以下账号密钥文件不存在，将跳过：")
        for account in missing_accounts:
            print(f"  - {account['key']}: {account['credentials_path']}")
    if not available_accounts:
        print("\n[失败] 没有可用的 GAM 密钥文件")
        return 1

    try:
        _require_googleads()
    except RuntimeError as exc:
        print(f"\n[失败] {exc}")
        return 1

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    failures: list[str] = []

    for account_index, account in enumerate(available_accounts, start=1):
        cfg = _merge_account_config(run_cfg, account)
        print(
            f"\n{'=' * 60}\n"
            f"账号 ({account_index}/{len(available_accounts)}): "
            f"{cfg['account_key']} / {cfg['network_code']}\n"
            f"{'=' * 60}"
        )
        print(f"密钥文件:     {cfg['credentials_path']}")
        print(f"应用名称:     {cfg['application_name']}")
        whitelist = cfg.get("product_whitelist") or []
        print(f"产品白名单:   {', '.join(whitelist) if whitelist else '（空 = 全量）'}")
        try:
            _run_account_fetch(cfg, report_specs, run_stamp=run_stamp)
        except Exception as exc:
            message = f"{cfg['account_key']}({cfg['network_code']}): {type(exc).__name__}: {exc}"
            failures.append(message)
            print(f"\n[失败] {message}")

    if failures:
        print("\n[失败] 部分账号拉数失败：")
        for message in failures:
            print(f"  - {message}")
        print(
            "\n常见原因：\n"
            "  1. 服务账号未在 GAM 后台授权（管理 → 全局设置 → API 访问）\n"
            "  2. networkCode 与密钥所属账号不匹配\n"
            "  3. API 版本不兼容（可设置 GAM_API_VERSION=v202605）\n"
            "  4. 报表维度/指标名称与当前账号权限不符"
        )
        return 1

    print(f"\n[成功] {len(available_accounts)} 个 GAM 账号数据已保存。")
    return 0


if __name__ == "__main__":
    # 作为脚本直接运行时，以进程退出码反映成功/失败
    sys.exit(main())
