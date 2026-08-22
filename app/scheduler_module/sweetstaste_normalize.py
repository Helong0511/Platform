"""
SweetStaste 上游报表字段规范化。

上游 ``/api/v1/get-ad-data`` 明细列多为 ``col_xxxxxxxx`` 哈希键，
稳定含义在同页 ``display_names`` 中（日期、域名、AdUnit、请求次数等）。
本模块把哈希列还原为平台入库用的稳定英文字段，并把 ``YYYY/MM/DD`` 转成 ``YYYY-MM-DD``。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.services.ad_data.watch_products import normalize_product_key

logger = logging.getLogger(__name__)

# 联调实测哈希（display_names 缺失时的兜底；优先仍走中文表头）
_SWEETSTASTE_HASH_FALLBACK: dict[str, str] = {
    "col_4ff1e74e": "date",
    "col_bfe68d58": "product_name",
    "adunit": "ad_unit",
    "col_dcb9d7fb": "request_count",
    "col_e4a8e2c0": "display_count",
    "col_9f4fc8a1": "display_rate",
    "col_3824fed5": "click_count",
    "ctr": "click_rate",
    "ecpm": "ecpm_before_deduct",
    "col_f90a1efc": "coverage_rate",
    "col_e8a1a321": "revenue_before_deduct",
}

# 短英文表头须整词匹配，避免 "electronic" 误命中 ctr
_EXACT_LABEL_TO_FIELD: dict[str, str] = {
    "ctr": "click_rate",
    "ecpm": "ecpm_before_deduct",
    "adunit": "ad_unit",
}

# 中文/长表头允许子串匹配（按长度降序，避免「请求数」先于「请求次数」误匹配）
_LABEL_TO_FIELD: tuple[tuple[str, str], ...] = (
    ("广告请求", "request_count"),
    ("请求次数", "request_count"),
    ("请求数", "request_count"),
    ("展示次数", "display_count"),
    ("展示数", "display_count"),
    ("展示率", "display_rate"),
    ("广告单元", "ad_unit"),
    ("匹配率", "coverage_rate"),
    ("预估收益", "revenue_before_deduct"),
    ("预计收益", "revenue_before_deduct"),
    ("点击数", "click_count"),
    ("日期", "date"),
    ("域名", "product_name"),
    ("链接", "product_name"),
    ("收益", "revenue_before_deduct"),
)

_PUNCT_RE = re.compile(r"[\s（）()%$＄：:]+")
_DATE_SLASH_RE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class SweetStasteRemapStats:
    """规范化统计，便于任务日志与对账。"""

    input_rows: int = 0
    kept_rows: int = 0
    dropped_non_dict: int = 0
    dropped_invalid_ad_unit: int = 0
    dropped_missing_required: int = 0
    dropped_bad_numeric: int = 0


def _normalize_label(label: str) -> str:
    return _PUNCT_RE.sub("", str(label or "").strip()).lower()


def _match_label_to_field(label_n: str) -> str | None:
    if not label_n:
        return None
    exact = _EXACT_LABEL_TO_FIELD.get(label_n)
    if exact:
        return exact
    for needle, dest in _LABEL_TO_FIELD:
        if needle.lower() in label_n or label_n == needle.lower():
            return dest
    return None


def resolve_sweetstaste_column_map(display_names: dict[str, Any] | None) -> dict[str, str]:
    """
    由 display_names 生成 原始列名 → 平台字段。

    哈希兜底始终生效；表头能识别时覆盖对应列。
    """
    mapping = dict(_SWEETSTASTE_HASH_FALLBACK)
    if not isinstance(display_names, dict):
        return mapping
    for raw_key, label in display_names.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        label_n = _normalize_label(str(label))
        field = _match_label_to_field(label_n)
        if field:
            mapping[key] = field
        elif key.lower() == "adunit":
            mapping[key] = "ad_unit"
    return mapping


def _normalize_date(value: Any) -> str:
    text = str(value or "").strip()
    matched = _DATE_SLASH_RE.match(text)
    if matched:
        year, month, day = matched.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    if _ISO_DATE_RE.match(text):
        return text
    return text.replace("/", "-") if text else ""


def _is_valid_date(value: str) -> bool:
    return bool(value and _ISO_DATE_RE.match(value))


def _coerce_int(value: Any) -> tuple[int, bool]:
    """
    解析整数。返回 (值, 是否成功)。

    空值视为 0 且成功；有值但无法解析则 ok=False。
    """
    if value is None or value == "":
        return 0, True
    try:
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if not text:
                return 0, True
            return int(float(text)), True
        return int(float(value)), True
    except (TypeError, ValueError):
        return 0, False


def _coerce_float(value: Any) -> tuple[float, bool]:
    if value is None or value == "":
        return 0.0, True
    try:
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if not text:
                return 0.0, True
            return float(text), True
        return float(value), True
    except (TypeError, ValueError):
        return 0.0, False


def _coverage_rate_to_fraction(value: float) -> float:
    """匹配率：上游可能是 0–100 百分比或 0–1 比例（对齐 Addermobi 口径）。"""
    if value <= 0:
        return 0.0
    return value / 100.0 if value > 1 else value


def normalize_sweetstaste_product_name(value: Any) -> str:
    """域名/链接归一为 host 小写，便于 products 表匹配。"""
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = normalize_product_key(raw)
    return normalized or raw


def is_valid_sweetstaste_ad_unit(ad_unit: Any) -> bool:
    """广告单元维度：丢弃空值、数字 0、字符串 0（date_link 汇总行）。"""
    if ad_unit is None:
        return False
    text = str(ad_unit).strip()
    if not text:
        return False
    if text in {"0", "0.0"}:
        return False
    return True


def remap_sweetstaste_rows(
    rows: list[Any],
    display_names: dict[str, Any] | None,
    *,
    stats: SweetStasteRemapStats | None = None,
) -> list[dict[str, Any]]:
    """把上游分页行映射为平台字段，并补匹配数、规范日期。"""
    col_map = resolve_sweetstaste_column_map(display_names)
    remapped: list[dict[str, Any]] = []
    st = stats if stats is not None else SweetStasteRemapStats()

    for row in rows or []:
        st.input_rows += 1
        if not isinstance(row, dict):
            st.dropped_non_dict += 1
            continue
        out: dict[str, Any] = {}
        for src_key, value in row.items():
            dest = col_map.get(str(src_key), "")
            if dest:
                out[dest] = value
        if "ad_unit" not in out and row.get("adunit") is not None:
            out["ad_unit"] = row.get("adunit")

        out["date"] = _normalize_date(out.get("date"))
        if not is_valid_sweetstaste_ad_unit(out.get("ad_unit")):
            st.dropped_invalid_ad_unit += 1
            continue

        out["ad_unit"] = str(out.get("ad_unit") or "").strip()
        out["product_name"] = normalize_sweetstaste_product_name(out.get("product_name"))

        if not _is_valid_date(out.get("date", "")) or not out["product_name"]:
            st.dropped_missing_required += 1
            continue

        request_count, req_ok = _coerce_int(out.get("request_count"))
        display_count, disp_ok = _coerce_int(out.get("display_count"))
        click_count, click_ok = _coerce_int(out.get("click_count"))
        revenue, rev_ok = _coerce_float(out.get("revenue_before_deduct"))
        ecpm, ecpm_ok = _coerce_float(out.get("ecpm_before_deduct"))
        coverage_raw, cov_ok = _coerce_float(out.get("coverage_rate"))

        if not all((req_ok, disp_ok, click_ok, rev_ok, ecpm_ok, cov_ok)):
            st.dropped_bad_numeric += 1
            continue

        out["request_count"] = request_count
        out["display_count"] = display_count
        out["click_count"] = click_count
        out["revenue_before_deduct"] = revenue
        out["ecpm_before_deduct"] = ecpm

        coverage_fraction = _coverage_rate_to_fraction(coverage_raw)
        if coverage_fraction > 0 and request_count > 0:
            out["match_count"] = int(round(request_count * coverage_fraction))
        else:
            out["match_count"] = 0

        remapped.append(out)
        st.kept_rows += 1

    dropped = (
        st.dropped_non_dict
        + st.dropped_invalid_ad_unit
        + st.dropped_missing_required
        + st.dropped_bad_numeric
    )
    if dropped:
        logger.info(
            "SweetStaste 行过滤：输入 %d，保留 %d，丢弃 %d "
            "(非 dict=%d, 无效单元=%d, 缺必填=%d, 数值异常=%d)",
            st.input_rows,
            st.kept_rows,
            dropped,
            st.dropped_non_dict,
            st.dropped_invalid_ad_unit,
            st.dropped_missing_required,
            st.dropped_bad_numeric,
        )
    return remapped
