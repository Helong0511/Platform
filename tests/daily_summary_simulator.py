"""
每日统计逻辑模拟器（纯内存，不依赖数据库）。

用于校验统计维度、筛选条件与分组聚合是否与 daily_summary_query 设计一致。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.core.constants import ECPM_MULTIPLIER, PERCENTAGE_MULTIPLIER
from app.services.ad_data.queries.dimension_filter import (
    ad_unit_exact_filter_applies,
    country_exact_filter_applies,
    normalize_dimension,
)

RawRow = Dict[str, Any]


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def row_matches_dimension(row: RawRow, dimension: Optional[str]) -> bool:
    """镜像 dimension_filter.build_ad_data_dimension_filter 的行级判断（明细列表）。"""
    dim = normalize_dimension(dimension)
    ad_unit = (row.get("ad_unit") or "").strip()
    country = (row.get("country_code") or "").strip()

    empty_ad_unit = not ad_unit
    has_country = bool(country)
    no_country = not has_country

    if dim == "country":
        return has_country and empty_ad_unit
    if dim == "ad_unit":
        return no_country and bool(ad_unit)
    return has_country and bool(ad_unit)


def row_matches_daily_summary_dimension(row: RawRow, dimension: Optional[str]) -> bool:
    """镜像 dimension_filter.build_daily_summary_dimension_filter 的行级判断（每日汇总）。"""
    dim = normalize_dimension(dimension)
    ad_unit = (row.get("ad_unit") or "").strip()
    country = (row.get("country_code") or "").strip()
    has_country = bool(country)

    if dim == "country":
        return has_country
    if dim == "ad_unit":
        return bool(ad_unit)
    return has_country and bool(ad_unit)


def row_matches_country_filter(row: RawRow, country_code: Optional[str]) -> bool:
    if not country_code or not str(country_code).strip():
        return True
    return (row.get("country_code") or "").strip() == str(country_code).strip()


def row_matches_ad_unit_filter(row: RawRow, ad_unit: Optional[str]) -> bool:
    if not ad_unit or not str(ad_unit).strip():
        return True
    return (row.get("ad_unit") or "").strip() == str(ad_unit).strip()


def row_matches_product_filter(row: RawRow, product_id: Optional[str]) -> bool:
    if not product_id or not str(product_id).strip():
        return True
    try:
        return int(row.get("product_id")) == int(product_id)
    except (TypeError, ValueError):
        return False


def row_matches_client_filter(row: RawRow, client_id: Optional[int]) -> bool:
    if client_id is None:
        return True
    return int(row.get("client_id")) == int(client_id)


def row_matches_date_range(
    row: RawRow,
    start_date: Optional[date],
    end_date: Optional[date],
) -> bool:
    row_date = _parse_date(row["date"])
    if start_date and row_date < start_date:
        return False
    if end_date and row_date > end_date:
        return False
    return True


def build_group_key(row: RawRow, dimension: Optional[str]) -> Tuple[Any, ...]:
    """镜像 DailySummaryQuery 的 GROUP BY 键。"""
    dim = normalize_dimension(dimension)
    key: List[Any] = [
        _parse_date(row["date"]).isoformat(),
        row["product_id"],
        row.get("product_name", ""),
        row["client_id"],
        row.get("client_name", ""),
        row.get("user_name", ""),
    ]
    if dim in ("ad_unit", "ad_unit_country"):
        key.append((row.get("ad_unit") or "").strip())
    return tuple(key)


def build_count_group_key(row: RawRow, dimension: Optional[str]) -> Tuple[Any, ...]:
    """镜像 _count_groups 的分组键（应与主查询一致）。"""
    dim = normalize_dimension(dimension)
    key: List[Any] = [_parse_date(row["date"]).isoformat(), row["product_id"], row["client_id"]]
    if dim in ("ad_unit", "ad_unit_country"):
        key.append((row.get("ad_unit") or "").strip())
    return tuple(key)


def aggregate_group(rows: Iterable[RawRow]) -> Dict[str, Any]:
    """汇总一组明细行并重算比率（镜像响应构建逻辑）。"""
    rows = list(rows)
    if not rows:
        raise ValueError("empty group")

    first = rows[0]
    totals = {
        "request_count": 0,
        "match_count": 0,
        "display_count": 0,
        "click_count": 0,
        "pageviews": 0,
        "revenue_after_deduct": 0.0,
        "revenue_before_deduct": 0.0,
        "cpc": 0.0,
        "viewability_sum": 0.0,
    }
    for row in rows:
        totals["request_count"] += int(row.get("request_count") or 0)
        totals["match_count"] += int(row.get("match_count") or 0)
        totals["display_count"] += int(row.get("display_count") or 0)
        totals["click_count"] += int(row.get("click_count") or 0)
        totals["pageviews"] += int(row.get("pageviews") or 0)
        totals["revenue_after_deduct"] += float(row.get("revenue_after_deduct") or 0)
        totals["revenue_before_deduct"] += float(row.get("revenue_before_deduct") or 0)
        totals["cpc"] += float(row.get("cpc") or 0)
        totals["viewability_sum"] += float(row.get("viewability_rate") or 0)

    req = totals["request_count"]
    match = totals["match_count"]
    disp = totals["display_count"]
    click = totals["click_count"]
    rev_after = totals["revenue_after_deduct"]
    rev_before = totals["revenue_before_deduct"]

    dim = normalize_dimension(first.get("_dimension"))
    group_by_ad_unit = dim in ("ad_unit", "ad_unit_country")

    return {
        "date": _parse_date(first["date"]).isoformat(),
        "product_id": first["product_id"],
        "product_name": first.get("product_name", ""),
        "client_id": first["client_id"],
        "client_name": first.get("client_name", ""),
        "user_name": first.get("user_name", ""),
        "ad_unit": (first.get("ad_unit") or "") if group_by_ad_unit else "",
        "country_code": "ZZ",
        "country_name_zh": "全部区域",
        "request_count": req,
        "match_count": match,
        "coverage_rate": round((match / req * PERCENTAGE_MULTIPLIER) if req else 0.0, 2),
        "display_count": disp,
        "display_rate": round((disp / match * PERCENTAGE_MULTIPLIER) if match else 0.0, 2),
        "click_count": click,
        "click_rate": round((click / disp * 100) if disp else 0.0, 2),
        "viewability_rate": round(totals["viewability_sum"] / len(rows), 2),
        "cpc": round(totals["cpc"], 2),
        "pageviews": totals["pageviews"],
        "ecpm_after_deduct": round(
            (rev_after / disp * ECPM_MULTIPLIER) if disp else 0.0, 4
        ),
        "revenue_after_deduct": round(rev_after, 4),
        "ecpm_before_deduct": round(
            (rev_before / disp * ECPM_MULTIPLIER) if disp else 0.0, 4
        ),
        "revenue_before_deduct": round(rev_before, 4),
    }


def filter_raw_rows(
    rows: List[RawRow],
    *,
    dimension: Optional[str] = None,
    client_id: Optional[int] = None,
    product_id: Optional[str] = None,
    country_code: Optional[str] = None,
    ad_unit: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user_id: Optional[int] = None,
    is_admin: bool = True,
) -> List[RawRow]:
    result = []
    for row in rows:
        if not row.get("product_active", True):
            continue
        if not is_admin and current_user_id is not None:
            if row.get("user_id") != current_user_id:
                continue
        if is_admin and client_id is not None and not row_matches_client_filter(row, client_id):
            continue
        if not row_matches_daily_summary_dimension(row, dimension):
            continue
        if not row_matches_product_filter(row, product_id):
            continue
        if country_exact_filter_applies(dimension) and not row_matches_country_filter(row, country_code):
            continue
        if ad_unit_exact_filter_applies(dimension) and not row_matches_ad_unit_filter(row, ad_unit):
            continue
        if not row_matches_date_range(row, start_date, end_date):
            continue
        tagged = dict(row)
        tagged["_dimension"] = normalize_dimension(dimension)
        result.append(tagged)
    return result


def simulate_daily_summary(
    rows: List[RawRow],
    *,
    dimension: Optional[str] = None,
    client_id: Optional[int] = None,
    product_id: Optional[str] = None,
    country_code: Optional[str] = None,
    ad_unit: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user_id: Optional[int] = None,
    is_admin: bool = True,
    page: int = 1,
    page_size: int = 100,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> Tuple[List[Dict[str, Any]], int]:
    """模拟每日汇总：筛选 → 分组聚合 → 排序 → 分页。"""
    filtered = filter_raw_rows(
        rows,
        dimension=dimension,
        client_id=client_id,
        product_id=product_id,
        country_code=country_code,
        ad_unit=ad_unit,
        start_date=start_date,
        end_date=end_date,
        current_user_id=current_user_id,
        is_admin=is_admin,
    )

    groups: Dict[Tuple[Any, ...], List[RawRow]] = defaultdict(list)
    for row in filtered:
        groups[build_group_key(row, dimension)].append(row)

    summaries = [aggregate_group(g) for g in groups.values()]

    reverse = sort_order.lower() == "desc"

    def sort_key(item: Dict[str, Any]):
        if sort_by == "date":
            return item["date"]
        if sort_by == "product":
            return item.get("product_name", "")
        if sort_by == "request_count":
            return item.get("request_count", 0)
        return item.get(sort_by, 0)

    summaries.sort(key=sort_key, reverse=reverse)

    total = len(summaries)
    offset = (page - 1) * page_size
    return summaries[offset : offset + page_size], total


def simulate_count_groups(
    rows: List[RawRow],
    *,
    dimension: Optional[str] = None,
    client_id: Optional[int] = None,
    product_id: Optional[str] = None,
    country_code: Optional[str] = None,
    ad_unit: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user_id: Optional[int] = None,
    is_admin: bool = True,
) -> int:
    filtered = filter_raw_rows(
        rows,
        dimension=dimension,
        client_id=client_id,
        product_id=product_id,
        country_code=country_code,
        ad_unit=ad_unit,
        start_date=start_date,
        end_date=end_date,
        current_user_id=current_user_id,
        is_admin=is_admin,
    )
    keys = {build_count_group_key(row, dimension) for row in filtered}
    return len(keys)
