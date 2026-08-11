"""
ad_data 上游元数据：数据来源、报表维度、账号。

report_type 枚举（与客户报表维度、唯一键一致）：
- unit    广告单元明细（有 ad_unit、无具体国家；含 country=ZZ）— ZhiSuo unit API、GAM ad_unit
- country 国家明细（有具体国家、无 ad_unit；不含 ZZ）— ZhiSuo country API、TQT/Huguang 等
- cross   具体国家+广告单元交叉（不含 ZZ）— Addermobi、Skymobi、Pomiad、GAM country 等
- daily   日汇总（无具体国家、无 ad_unit；含 country=ZZ）— ZhiSuo daily 兜底、GAM daily
- legacy  历史/待标注；新入库一律按行形态自动推断为 unit/country/cross/daily

ZZ（全部区域）不算具体国家：ZZ+有广告单元→unit；ZZ+无广告单元→daily。
"""
from __future__ import annotations

from typing import Optional

from app.core.country_code import has_concrete_country_code

# 数据来源（与定时拉数任务 / 入库 data_source 字段一致，使用小写英文 slug）
DATA_SOURCE_ZHISUO = "zhisuo"
DATA_SOURCE_GAM = "gam"
DATA_SOURCE_POMIAD = "pomiad"
DATA_SOURCE_H5DEER = "h5deer"
DATA_SOURCE_ADDERMOBI = "addermobi"
DATA_SOURCE_SKYMOBI = "skymobi"
DATA_SOURCE_HUGUANG = "huguang"
DATA_SOURCE_TQT = "tqt"
DATA_SOURCE_TBSJ = "tbsj"  # yangyangdeyi / 通百世家
DATA_SOURCE_AYA = "aya"
DATA_SOURCE_FLYMOBI = "flymobi"
DATA_SOURCE_LEIYANG = "leiyang"
DATA_SOURCE_EXCEL = "excel"
DATA_SOURCE_UNKNOWN = "unknown"
DATA_SOURCE_LEGACY = "legacy"

# 上游 API 自动拉数来源（编辑下拉优先展示）
UPSTREAM_API_DATA_SOURCES: tuple[str, ...] = (
    DATA_SOURCE_ZHISUO,
    DATA_SOURCE_GAM,
    DATA_SOURCE_POMIAD,
    DATA_SOURCE_H5DEER,
    DATA_SOURCE_ADDERMOBI,
    DATA_SOURCE_SKYMOBI,
    DATA_SOURCE_HUGUANG,
    DATA_SOURCE_TQT,
    DATA_SOURCE_TBSJ,
    DATA_SOURCE_AYA,
    DATA_SOURCE_FLYMOBI,
    DATA_SOURCE_LEIYANG,
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

# 每日汇总选源优先级（同一产品+日期 API 侧只计一套；Excel 日报可与国家相加）
# country > cross > unit > daily（API 日报）；实现见 dimension_filter
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
    """
    根据行形态推断报表维度（历史回填与 legacy 入库自动标注）。

    ZZ（全部区域）视为无具体国家：有广告单元→unit，无广告单元→daily。
    """
    has_unit = bool(str(ad_unit or "").strip())
    has_country = has_concrete_country_code(country_code)
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
    """
    入库单行 report_type。

    上游已明确维度（非 legacy）时直接使用；否则按 ad_unit / country_code 行形态推断。
    """
    normalized = normalize_report_type(explicit)
    if normalized != REPORT_TYPE_LEGACY:
        return normalized
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
    DATA_SOURCE_ZHISUO: "ZhiSuo",
    DATA_SOURCE_GAM: "GAM",
    DATA_SOURCE_POMIAD: "Pomiad",
    DATA_SOURCE_H5DEER: "H5 Deer",
    DATA_SOURCE_ADDERMOBI: "Addermobi",
    DATA_SOURCE_SKYMOBI: "Skymobi",
    DATA_SOURCE_HUGUANG: "Huguang",
    DATA_SOURCE_TQT: "TQT",
    DATA_SOURCE_TBSJ: "通百世家(yangyangdeyi)",
    DATA_SOURCE_AYA: "Aya",
    DATA_SOURCE_FLYMOBI: "FlyMobi",
    DATA_SOURCE_LEIYANG: "LeiYang",
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
    REPORT_TYPE_UNIT: "按广告单元，无具体国家（含 ZZ）；ZhiSuo channelunit、GAM ad_unit、Aya getAdsDataUnit、LeiYang ad-unit（默认关）",
    REPORT_TYPE_COUNTRY: "按具体国家，无广告单元（不含 ZZ）；ZhiSuo channelcountry、TQT、Huguang、Aya、LeiYang country（默认关）",
    REPORT_TYPE_CROSS: "具体国家+广告单元（不含 ZZ）；ZhiSuo channeldata、Addermobi、Skymobi、Pomiad、H5 Deer、FlyMobi countryList、GAM country、TBSJ(yangyangdeyi)/adunit、LeiYang atomic（推荐）",
    REPORT_TYPE_DAILY: "日汇总，无具体国家无单元（含 ZZ）；ZhiSuo channeldaily 兜底、GAM daily、Aya getDay、LeiYang all（默认关）",
    REPORT_TYPE_LEGACY: "历史或未标注；新入库会自动按行形态推断",
}

# 各上游 API 默认报表维度（入库时按行形态自动推断，此处仅作文档/兼容）
UPSTREAM_DEFAULT_REPORT_TYPES: dict[str, str] = {
    DATA_SOURCE_ZHISUO: REPORT_TYPE_LEGACY,
    DATA_SOURCE_GAM: REPORT_TYPE_LEGACY,
    DATA_SOURCE_POMIAD: REPORT_TYPE_LEGACY,
    DATA_SOURCE_H5DEER: REPORT_TYPE_LEGACY,
    DATA_SOURCE_ADDERMOBI: REPORT_TYPE_LEGACY,
    DATA_SOURCE_SKYMOBI: REPORT_TYPE_LEGACY,
    DATA_SOURCE_HUGUANG: REPORT_TYPE_LEGACY,
    DATA_SOURCE_TQT: REPORT_TYPE_LEGACY,
    DATA_SOURCE_TBSJ: REPORT_TYPE_CROSS,  # /adunit 实为国家+广告单元交叉
    DATA_SOURCE_AYA: REPORT_TYPE_LEGACY,
    DATA_SOURCE_FLYMOBI: REPORT_TYPE_LEGACY,
    DATA_SOURCE_LEIYANG: REPORT_TYPE_CROSS,  # 默认 /reports/atomic（国家+广告单元）
    DATA_SOURCE_EXCEL: REPORT_TYPE_DAILY,
}


def format_data_source_label(value: Optional[str]) -> str:
    key = str(value or DATA_SOURCE_LEGACY).strip().lower() or DATA_SOURCE_LEGACY
    return DATA_SOURCE_LABELS.get(key, key)


def format_report_type_label(value: Optional[str]) -> str:
    key = normalize_report_type(value)
    return REPORT_TYPE_LABELS.get(key, key)


def build_ad_data_metadata_catalog() -> dict:
    """
    管理端下拉目录：数据来源 / 报表类型（以后端 ad_data_metadata 为唯一真相源）。

    前端应调用 GET /api/v1/ad-data/metadata-options 拉取，避免每增上游就改前端常量。
    """
    manual_sources = (
        DATA_SOURCE_EXCEL,
        DATA_SOURCE_LEGACY,
        DATA_SOURCE_UNKNOWN,
    )
    detail_report_types = tuple(REPORT_TYPE_DETAIL_OPTIONS)
    other_report_types = (REPORT_TYPE_LEGACY,)

    def _source_item(slug: str) -> dict:
        return {"value": slug, "label": format_data_source_label(slug)}

    def _report_item(slug: str) -> dict:
        return {
            "value": slug,
            "label": format_report_type_label(slug),
            "hint": REPORT_TYPE_HINTS.get(slug, ""),
        }

    return {
        "data_sources": {
            "upstream": [_source_item(s) for s in UPSTREAM_API_DATA_SOURCES],
            "manual": [_source_item(s) for s in manual_sources],
            "labels": {k: format_data_source_label(k) for k in VALID_DATA_SOURCES},
        },
        "report_types": {
            "detail": [_report_item(t) for t in detail_report_types],
            "other": [_report_item(t) for t in other_report_types],
            "labels": {k: format_report_type_label(k) for k in VALID_REPORT_TYPES},
            "hints": dict(REPORT_TYPE_HINTS),
        },
    }


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
