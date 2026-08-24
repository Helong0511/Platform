"""
PlayHorizonx 上游 /reports/index 行规范化。

实测响应含 date、url、com_name、country_code 及指标字段。
cross 入库须同时有具体国家与非空广告单元；缺必填或汇总行跳过并记统计。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.core.ad_data_metadata import REPORT_TYPE_CROSS, REPORT_TYPE_UNIT
from app.core.country_code import ALL_REGIONS_COUNTRY_CODE, has_concrete_country_code

logger = logging.getLogger(__name__)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class PlayHorizonxNormalizeStats:
    input_rows: int = 0
    kept_rows: int = 0
    dropped_non_dict: int = 0
    dropped_missing_required: int = 0
    dropped_invalid_cross_shape: int = 0
    dropped_invalid_date: int = 0


def _normalize_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or not _ISO_DATE_RE.match(text):
        return None
    return text


def _normalize_ad_unit(value: Any) -> str:
    text = str(value or "").strip()
    if text in ("0", "null", "None"):
        return ""
    return text


def _normalize_country_for_cross(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text or text == ALL_REGIONS_COUNTRY_CODE:
        return None
    if not has_concrete_country_code(text):
        return None
    return text


def normalize_playhorizonx_rows(
    rows: list[Any],
    *,
    report_type: str,
) -> tuple[list[dict[str, Any]], PlayHorizonxNormalizeStats]:
    """
    规范化 PlayHorizonx 原始行，供 import_upstream_ad_data 入库。

    - cross：保留 country_code + com_name，缺任一必填则跳过
    - unit（兼容）：剥离 country_code，避免 unit 类型却带国家导致每日统计不可见
    """
    stats = PlayHorizonxNormalizeStats(input_rows=len(rows or []))
    normalized: list[dict[str, Any]] = []
    is_cross = str(report_type or "").strip().lower() == REPORT_TYPE_CROSS

    for raw in rows or []:
        if not isinstance(raw, dict):
            stats.dropped_non_dict += 1
            continue

        date_str = _normalize_date(raw.get("date"))
        product_name = str(raw.get("url") or "").strip()
        ad_unit = _normalize_ad_unit(raw.get("com_name"))
        country_raw = raw.get("country_code")

        if not date_str or not product_name:
            stats.dropped_missing_required += 1
            continue

        if is_cross:
            country_code = _normalize_country_for_cross(country_raw)
            if not country_code or not ad_unit:
                stats.dropped_invalid_cross_shape += 1
                continue
            item = dict(raw)
            item["date"] = date_str
            item["url"] = product_name
            item["com_name"] = ad_unit
            item["country_code"] = country_code
        else:
            if not ad_unit:
                stats.dropped_missing_required += 1
                continue
            item = dict(raw)
            item["date"] = date_str
            item["url"] = product_name
            item["com_name"] = ad_unit
            item.pop("country_code", None)

        normalized.append(item)
        stats.kept_rows += 1

    if stats.dropped_invalid_cross_shape or stats.dropped_missing_required:
        logger.info(
            "PlayHorizonx 规范化: 输入=%s 保留=%s 缺必填=%s cross形态无效=%s 非dict=%s",
            stats.input_rows,
            stats.kept_rows,
            stats.dropped_missing_required,
            stats.dropped_invalid_cross_shape,
            stats.dropped_non_dict,
        )

    return normalized, stats


def make_playhorizonx_transform(report_type: str):
    """返回 run_upstream_import_task 可用的 data_transform 闭包。"""

    def _transform(rows: list[Any]) -> list[dict[str, Any]]:
        normalized, _ = normalize_playhorizonx_rows(rows, report_type=report_type)
        return normalized

    return _transform
