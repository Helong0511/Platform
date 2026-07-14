"""
ad_data 上游元数据：数据来源、报表维度、账号。

report_type 枚举（与客户报表维度、唯一键一致）：
- unit    广告单元明细（有 ad_unit、无 country）— 智索 unit API、GAM ad_unit
- country 国家明细（有 country、无 ad_unit）— 智索 country API、TQT/Huguang 等
- cross   国家+广告单元交叉 — Addermobi、Skymobi、Pomiad、GAM country 等
- daily   日汇总（无 country、无 ad_unit）— 智索 daily 兜底、GAM daily
- legacy  历史/待标注；新入库一律按行形态自动推断为 unit/country/cross/daily
"""
from __future__ import annotations

from typing import Optional

# 数据来源（与定时拉数任务 / 入库 data_source 字段一致，使用小写英文 slug）
DATA_SOURCE_ZHISUO = "zhisuo"
DATA_SOURCE_GAM = "gam"
DATA_SOURCE_POMIAD = "pomiad"
DATA_SOURCE_ADDERMOBI = "addermobi"
DATA_SOURCE_SKYMOBI = "skymobi"
DATA_SOURCE_HUGUANG = "huguang"
DATA_SOURCE_TQT = "tqt"
DATA_SOURCE_TBSJ = "tbsj"  # yangyangdeyi / 通百世家
DATA_SOURCE_EXCEL = "excel"
DATA_SOURCE_UNKNOWN = "unknown"
DATA_SOURCE_LEGACY = "legacy"

# 上游 API 自动拉数来源（编辑下拉优先展示）
UPSTREAM_API_DATA_SOURCES: tuple[str, ...] = (
    DATA_SOURCE_ZHISUO,
    DATA_SOURCE_GAM,
    DATA_SOURCE_POMIAD,
    DATA_SOURCE_ADDERMOBI,
    DATA_SOURCE_SKYMOBI,
    DATA_SOURCE_HUGUANG,
    DATA_SOURCE_TQT,
    DATA_SOURCE_TBSJ,
)

VALID_DATA_SOURCES = frozenset({
    *UPSTREAM_API_DATA_SOURCES,
    DATA_SOURCE_EXCEL,
    DATA_SOURCE_UNKNOWN,
    DATA_SOURCE_LEGACY,
})

# 报表维度 / 颗粒度
REPORT_TYPE_UNIT = "unit"
REPORT_TYPE_COUNTRY = "country"
REPORT_TYPE_CROSS = "cross"
REPORT_TYPE_DAILY = "daily"
REPORT_TYPE_LEGACY = "legacy"

VALID_REPORT_TYPES = frozenset({
    REPORT_TYPE_UNIT,
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_CROSS,
    REPORT_TYPE_DAILY,
    REPORT_TYPE_LEGACY,
})

# 明细列表维度 → 纳入的 report_type
DIMENSION_REPORT_TYPES: dict[str, tuple[str, ...]] = {
    "country": (REPORT_TYPE_COUNTRY,),
    "ad_unit": (REPORT_TYPE_UNIT,),
    "ad_unit_country": (REPORT_TYPE_CROSS,),
}

# 每日汇总选源优先级（同一产品+日期只计一套）
SUMMARY_REPORT_TYPE_PRIORITY: tuple[str, ...] = (
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_CROSS,
    REPORT_TYPE_UNIT,
    REPORT_TYPE_DAILY,
)


def normalize_report_type(value: Optional[str]) -> str:
    text = str(value or "").strip().lower()
    if text in VALID_REPORT_TYPES:
        return text
    return REPORT_TYPE_LEGACY


def normalize_data_source(value: Optional[str]) -> str:
    text = str(value or "").strip().lower()
    if text in VALID_DATA_SOURCES:
        return text
    # 允许管理员手动录入新 slug（字母数字下划线）
    if text and len(text) <= 32 and all(ch.isalnum() or ch == "_" for ch in text):
        return text
    return DATA_SOURCE_LEGACY


def normalize_upstream_account(value: Optional[str]) -> str:
    return str(value or "").strip()[:64]


def infer_report_type_from_shape(
    *,
    ad_unit: str = "",
    country_code: Optional[str] = None,
) -> str:
    """根据行形态推断报表维度（历史回填与 legacy 入库自动标注）。"""
    has_unit = bool(str(ad_unit or "").strip())
    has_country = bool(str(country_code or "").strip())
    if has_unit and has_country:
        return REPORT_TYPE_CROSS
    if has_country:
        return REPORT_TYPE_COUNTRY
    if has_unit:
        return REPORT_TYPE_UNIT
    return REPORT_TYPE_DAILY


def resolve_report_type_for_row(
    explicit: Optional[str],
    *,
    ad_unit: str = "",
    country_code: Optional[str] = None,
) -> str:
    """入库单行 report_type：按 ad_unit / country_code 行形态自动推断。"""
    del explicit
    return infer_report_type_from_shape(ad_unit=ad_unit, country_code=country_code)


def format_report_type_counts_for_notify(
    counts: Optional[dict[str, int]],
) -> str:
    """将入库统计中的报表类型计数格式化为 Telegram 通知文案。"""
    if not counts:
        return ""
    parts: list[str] = []
    for key in REPORT_TYPE_DETAIL_OPTIONS:
        count = int(counts.get(key) or 0)
        if count <= 0:
            continue
        label = REPORT_TYPE_LABELS.get(key, key)
        parts.append(f"{label}({key}) {count}条")
    legacy_count = int(counts.get(REPORT_TYPE_LEGACY) or 0)
    if legacy_count > 0:
        parts.append(f"{REPORT_TYPE_LABELS[REPORT_TYPE_LEGACY]}({REPORT_TYPE_LEGACY}) {legacy_count}条")
    return "、".join(parts)


def get_report_type_options_for_admin() -> list[dict[str, str]]:
    """管理端报表类型下拉选项（含说明）。"""
    options: list[dict[str, str]] = []
    for key in (*REPORT_TYPE_DETAIL_OPTIONS, REPORT_TYPE_LEGACY):
        options.append(
            {
                "value": key,
                "label": REPORT_TYPE_LABELS[key],
                "hint": REPORT_TYPE_HINTS.get(key, ""),
            }
        )
    return options


def gam_report_key_to_report_type(report_key: str) -> str:
    """GAM 报表键 → ad_data.report_type。"""
    key = str(report_key or "").strip().lower()
    if key == "country":
        return REPORT_TYPE_CROSS
    if key == "ad_unit":
        return REPORT_TYPE_UNIT
    if key == "daily":
        return REPORT_TYPE_DAILY
    return REPORT_TYPE_LEGACY


# 管理端展示用中文标签
DATA_SOURCE_LABELS: dict[str, str] = {
    DATA_SOURCE_ZHISUO: "智索",
    DATA_SOURCE_GAM: "GAM",
    DATA_SOURCE_POMIAD: "Pomiad",
    DATA_SOURCE_ADDERMOBI: "Addermobi",
    DATA_SOURCE_SKYMOBI: "Skymobi",
    DATA_SOURCE_HUGUANG: "Huguang",
    DATA_SOURCE_TQT: "TQT",
    DATA_SOURCE_TBSJ: "通百世家(yangyangdeyi)",
    DATA_SOURCE_EXCEL: "Excel 导入",
    DATA_SOURCE_LEGACY: "历史",
    DATA_SOURCE_UNKNOWN: "未知",
}

REPORT_TYPE_LABELS: dict[str, str] = {
    REPORT_TYPE_UNIT: "广告单元",
    REPORT_TYPE_COUNTRY: "国家",
    REPORT_TYPE_CROSS: "交叉",
    REPORT_TYPE_DAILY: "日报",
    REPORT_TYPE_LEGACY: "历史",
}

# 管理端编辑下拉：统计维度（优先）
REPORT_TYPE_DETAIL_OPTIONS: tuple[str, ...] = (
    REPORT_TYPE_UNIT,
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_CROSS,
    REPORT_TYPE_DAILY,
)

REPORT_TYPE_HINTS: dict[str, str] = {
    REPORT_TYPE_UNIT: "按广告单元，无国家；智索 channelunit、GAM ad_unit",
    REPORT_TYPE_COUNTRY: "按国家，无广告单元；智索 channelcountry、TQT、Huguang",
    REPORT_TYPE_CROSS: "国家+广告单元；智索 channeldata、Addermobi、Skymobi、Pomiad、GAM country",
    REPORT_TYPE_DAILY: "日汇总，无国家无单元；智索 channeldaily 兜底、GAM daily",
    REPORT_TYPE_LEGACY: "历史或未标注；新入库会自动按行形态推断",
}

# 各上游 API 默认报表维度（入库时按行形态自动推断，此处仅作文档/兼容）
UPSTREAM_DEFAULT_REPORT_TYPES: dict[str, str] = {
    DATA_SOURCE_ZHISUO: REPORT_TYPE_LEGACY,
    DATA_SOURCE_GAM: REPORT_TYPE_LEGACY,
    DATA_SOURCE_POMIAD: REPORT_TYPE_LEGACY,
    DATA_SOURCE_ADDERMOBI: REPORT_TYPE_LEGACY,
    DATA_SOURCE_SKYMOBI: REPORT_TYPE_LEGACY,
    DATA_SOURCE_HUGUANG: REPORT_TYPE_LEGACY,
    DATA_SOURCE_TQT: REPORT_TYPE_LEGACY,
    DATA_SOURCE_TBSJ: REPORT_TYPE_LEGACY,
    DATA_SOURCE_EXCEL: REPORT_TYPE_LEGACY,
}


def format_data_source_label(value: Optional[str]) -> str:
    key = str(value or DATA_SOURCE_LEGACY).strip().lower() or DATA_SOURCE_LEGACY
    return DATA_SOURCE_LABELS.get(key, key)


def format_report_type_label(value: Optional[str]) -> str:
    key = normalize_report_type(value)
    return REPORT_TYPE_LABELS.get(key, key)


# DECIMAL(7,4) 比率字段合法范围（百分比数值）
AD_DATA_RATE_MIN = -999.9999
AD_DATA_RATE_MAX = 999.9999


def clamp_ad_data_rate(value: Optional[float | int | str]) -> float:
    """将覆盖率/展示率等比率裁剪到数据库 DECIMAL(7,4) 合法范围。"""
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(AD_DATA_RATE_MIN, min(AD_DATA_RATE_MAX, numeric))


def clamp_ad_data_money(value: Optional[float | int | str]) -> float:
    """金额类字段安全转 float（DECIMAL(12,4) 由数据库约束）。"""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
