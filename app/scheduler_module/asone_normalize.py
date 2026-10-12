"""
Asone 渠道报表行规范化。

实测字段（camelCase）：
- reportDate (YYYY-MM-DD 字符串)
- domainName (域名，作产品名)
- country (英文全称，如 UNITED STATES；unit/daily 接口常无此字段)
- unitId (字符串广告位 ID；country/daily 接口常无)
- requests / matchedRequests / impressions / clicks (整数或可转整数)
- estimatedEarnings (浮点收益 USD)
- ecpm (文档有；实测可能缺，入库时可按收益/展示回算)

维度形态：
- cross（明细 channel-data-report）：保留具体国家 + unitId
- country：保留国家，清空广告单元
- unit：保留 unitId，清空国家
- daily：清空国家与广告单元
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.core.ad_data_metadata import (
    REPORT_TYPE_COUNTRY,
    REPORT_TYPE_CROSS,
    REPORT_TYPE_DAILY,
    REPORT_TYPE_UNIT,
)
from app.core.country_code import (
    ALL_REGIONS_COUNTRY_CODE,
    _lookup_common_english_alias,
    has_concrete_country_code,
)

logger = logging.getLogger(__name__)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass
class AsoneNormalizeStats:
    input_rows: int = 0
    kept_rows: int = 0
    dropped_non_dict: int = 0
    dropped_missing_required: int = 0
    dropped_invalid_shape: int = 0
    country_alias_hits: int = 0


def _pick(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item.get(key) is not None and str(item.get(key)).strip() != "":
            return item.get(key)
    return None


def _normalize_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if _ISO_DATE_RE.match(text):
        return text[:10]
    return None


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _normalize_country(value: Any, *, stats: AsoneNormalizeStats) -> str:
    """英文全称优先走内置别名转 ISO；未命中保留原文供入库 DB 解析。"""
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in {
        "ALL",
        "ALL REGIONS",
        "WORLD",
        ALL_REGIONS_COUNTRY_CODE,
        "全球",
        "全部",
        "NONE",
        "NULL",
        "N/A",
        "NA",
        "UNKNOWN",
        "--",
    }:
        return ""
    aliased = _lookup_common_english_alias(text)
    if aliased:
        stats.country_alias_hits += 1
        return aliased
    # 已是二字母则大写
    if len(text) == 2 and text.isalpha():
        return upper
    return text


def _normalize_ad_unit(value: Any) -> str:
    text = str(value or "").strip()
    if text in ("0", "null", "None", "-"):
        return ""
    return text


def normalize_asone_rows(
    rows: list[Any],
    *,
    report_type: str,
) -> tuple[list[dict[str, Any]], AsoneNormalizeStats]:
    """将 Asone 原始行规范为平台可映射字段，并按维度裁剪形态。"""
    stats = AsoneNormalizeStats(input_rows=len(rows or []))
    out: list[dict[str, Any]] = []
    rt = str(report_type or "").strip().lower()

    for raw in rows or []:
        if not isinstance(raw, dict):
            stats.dropped_non_dict += 1
            continue

        date_str = _normalize_date(_pick(raw, "reportDate", "report_date", "date"))
        product_name = str(_pick(raw, "domainName", "domain_name", "domain") or "").strip()
        if not date_str or not product_name:
            stats.dropped_missing_required += 1
            continue

        country = _normalize_country(_pick(raw, "country", "countryCode", "country_code"), stats=stats)
        ad_unit = _normalize_ad_unit(_pick(raw, "unitId", "unit_id", "adUnit", "ad_unit"))

        item: dict[str, Any] = {
            "date": date_str,
            "product_name": product_name,
            "request_count": _to_int(_pick(raw, "requests", "request")),
            "match_count": _to_int(_pick(raw, "matchedRequests", "matched_requests", "matchRequests")),
            "display_count": _to_int(_pick(raw, "impressions", "impression")),
            "click_count": _to_int(_pick(raw, "clicks", "click")),
            "revenue_before_deduct": _to_float(
                _pick(raw, "estimatedEarnings", "estimated_earnings", "revenue")
            ),
            "ecpm_before_deduct": _to_float(_pick(raw, "ecpm", "eCPM", "Ecpm")),
        }

        if rt == REPORT_TYPE_CROSS:
            if not has_concrete_country_code(country) or not ad_unit:
                stats.dropped_invalid_shape += 1
                continue
            item["country_code"] = country
            item["ad_unit"] = ad_unit
        elif rt == REPORT_TYPE_COUNTRY:
            if not has_concrete_country_code(country):
                stats.dropped_invalid_shape += 1
                continue
            item["country_code"] = country
            item["ad_unit"] = ""
        elif rt == REPORT_TYPE_UNIT:
            if not ad_unit:
                stats.dropped_invalid_shape += 1
                continue
            item["country_code"] = ""
            item["ad_unit"] = ad_unit
        elif rt == REPORT_TYPE_DAILY:
            item["country_code"] = ""
            item["ad_unit"] = ""
        else:
            item["country_code"] = country
            item["ad_unit"] = ad_unit

        out.append(item)
        stats.kept_rows += 1

    if stats.dropped_invalid_shape or stats.dropped_missing_required:
        logger.info(
            "Asone 规范化: 输入=%s 保留=%s 缺必填=%s 形态无效=%s 非dict=%s 国名别名=%s",
            stats.input_rows,
            stats.kept_rows,
            stats.dropped_missing_required,
            stats.dropped_invalid_shape,
            stats.dropped_non_dict,
            stats.country_alias_hits,
        )
    return out, stats


def make_asone_transform(report_type: str):
    """返回 run_upstream_import_task 可用的 data_transform。"""

    def _transform(rows: list[Any]) -> list[dict[str, Any]]:
        normalized, _ = normalize_asone_rows(rows, report_type=report_type)
        return normalized

    return _transform
