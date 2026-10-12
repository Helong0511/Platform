"""Asone 各维度报表汇总一致性比对（有数据后跑；不入库）。

用法：
  set ASONE_API_KEY=...
  python tests/test_asone_dimension_consistency.py
  python tests/test_asone_dimension_consistency.py --start 2026-10-01 --end 2026-10-12

比对口径（按 reportDate 汇总后互相对齐）：
  - detail(明细/交叉) vs country / unit / daily
  - 指标：requests / matchedRequests / impressions / clicks / estimatedEarnings
  - 允许绝对误差：整数指标 0；金额默认 0.01
无任何维度数据时退出码 3（不足以做一致性结论）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

API_KEY = (os.getenv("ASONE_API_KEY") or "").strip()
BASE = os.getenv("ASONE_API_BASE_URL", "https://asone.club").rstrip("/")
PAGE_SIZE = int(os.getenv("ASONE_API_PAGE_SIZE", "200"))
MONEY_TOLERANCE = Decimal(os.getenv("ASONE_MONEY_TOLERANCE", "0.01"))

ENDPOINTS: dict[str, str] = {
    "detail": "/api/channel-data-report/apiPage",
    "unit": "/api/channel-unit-report/apiPage",
    "country": "/api/channel-country-report/apiPage",
    "daily": "/api/channel-daily-report/apiPage",
}

METRIC_KEYS = (
    "requests",
    "matchedRequests",
    "impressions",
    "clicks",
    "estimatedEarnings",
)


@dataclass
class DayAgg:
    requests: Decimal = Decimal("0")
    matchedRequests: Decimal = Decimal("0")
    impressions: Decimal = Decimal("0")
    clicks: Decimal = Decimal("0")
    estimatedEarnings: Decimal = Decimal("0")
    rows: int = 0

    def add_row(self, row: dict[str, Any]) -> None:
        self.rows += 1
        for key in METRIC_KEYS:
            self.__dict__[key] += _to_decimal(row.get(key))


def _to_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_date(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code} {path}: {raw[:500]}") from e


def fetch_all_rows(name: str, start: date, end: date) -> list[dict[str, Any]]:
    path = ENDPOINTS[name]
    rows: list[dict[str, Any]] = []
    current = 1
    pages = 1
    while current <= pages:
        payload = {
            "current": current,
            "size": PAGE_SIZE,
            "reportDateStart": start.isoformat(),
            "reportDateEnd": end.isoformat(),
            "orders": [{"column": "reportDate", "asc": False}],
        }
        data = post_json(path, payload)
        if not data.get("success"):
            raise RuntimeError(f"{name} 失败: {data}")
        page = data.get("data") or {}
        batch = page.get("records") or []
        rows.extend(batch)
        pages = int(page.get("pages") or 1)
        total = int(page.get("total") or 0)
        print(f"  [{name}] page {current}/{pages} got={len(batch)} total={total}")
        if not batch:
            break
        current += 1
    return rows


def aggregate_by_date(rows: list[dict[str, Any]]) -> dict[str, DayAgg]:
    out: dict[str, DayAgg] = defaultdict(DayAgg)
    for row in rows:
        day = str(row.get("reportDate") or "").strip()
        if not day:
            continue
        out[day].add_row(row)
    return dict(out)


def totals(aggs: dict[str, DayAgg]) -> DayAgg:
    total = DayAgg()
    for day_agg in aggs.values():
        total.rows += day_agg.rows
        for key in METRIC_KEYS:
            total.__dict__[key] += day_agg.__dict__[key]
    return total


def metric_close(a: Decimal, b: Decimal, *, money: bool) -> bool:
    if money:
        return abs(a - b) <= MONEY_TOLERANCE
    return a == b


def compare_dims(
    left_name: str,
    left: dict[str, DayAgg],
    right_name: str,
    right: dict[str, DayAgg],
) -> list[str]:
    issues: list[str] = []
    days = sorted(set(left) | set(right))
    for day in days:
        la = left.get(day) or DayAgg()
        ra = right.get(day) or DayAgg()
        for key in METRIC_KEYS:
            money = key == "estimatedEarnings"
            lv = la.__dict__[key]
            rv = ra.__dict__[key]
            if not metric_close(lv, rv, money=money):
                issues.append(
                    f"{day} {left_name}.{key}={lv} vs {right_name}.{key}={rv} "
                    f"delta={lv - rv}"
                )
    # 总量再核一次
    lt = totals(left)
    rt = totals(right)
    for key in METRIC_KEYS:
        money = key == "estimatedEarnings"
        lv = lt.__dict__[key]
        rv = rt.__dict__[key]
        if not metric_close(lv, rv, money=money):
            issues.append(
                f"TOTAL {left_name}.{key}={lv} vs {right_name}.{key}={rv} "
                f"delta={lv - rv}"
            )
    return issues


def fmt_agg(name: str, agg: DayAgg) -> str:
    return (
        f"{name}: rows={agg.rows} req={agg.requests} matched={agg.matchedRequests} "
        f"imp={agg.impressions} clk={agg.clicks} rev={agg.estimatedEarnings}"
    )


def main() -> int:
    if not API_KEY:
        print("请设置环境变量 ASONE_API_KEY", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(description="Asone 维度一致性比对")
    today = date.today()
    parser.add_argument("--start", default=(today - timedelta(days=30)).isoformat())
    parser.add_argument("--end", default=today.isoformat())
    args = parser.parse_args()
    start = _parse_date(args.start)
    end = _parse_date(args.end)

    print(f"BASE={BASE}")
    print(f"RANGE={start}~{end}")
    print(f"MONEY_TOLERANCE={MONEY_TOLERANCE}")

    by_dim_rows: dict[str, list[dict[str, Any]]] = {}
    by_dim_agg: dict[str, dict[str, DayAgg]] = {}
    for name in ENDPOINTS:
        print(f"\n==== fetch {name} ====")
        rows = fetch_all_rows(name, start, end)
        by_dim_rows[name] = rows
        by_dim_agg[name] = aggregate_by_date(rows)
        print(fmt_agg(name, totals(by_dim_agg[name])))
        if rows:
            sample = rows[0]
            print("sample keys:", sorted(sample.keys()))
            print("sample:", json.dumps(sample, ensure_ascii=False))

    total_rows = sum(len(v) for v in by_dim_rows.values())
    if total_rows == 0:
        print("\n结论: 所选区间四个维度均无数据，无法做一致性比对（exit=3）")
        return 3

    # 以明细为基准（若明细为空，则用行数最多的维度作基准）
    baseline = "detail" if by_dim_rows["detail"] else max(
        by_dim_rows, key=lambda k: len(by_dim_rows[k])
    )
    print(f"\n基准维度: {baseline}")

    all_issues: list[str] = []
    for name in ENDPOINTS:
        if name == baseline:
            continue
        if not by_dim_rows[name] and not by_dim_rows[baseline]:
            continue
        issues = compare_dims(baseline, by_dim_agg[baseline], name, by_dim_agg[name])
        if issues:
            print(f"\n不一致: {baseline} vs {name} ({len(issues)} 项)")
            for item in issues[:50]:
                print("  -", item)
            if len(issues) > 50:
                print(f"  ... 另有 {len(issues) - 50} 项")
            all_issues.extend(issues)
        else:
            print(f"一致: {baseline} vs {name}")

    if all_issues:
        print(f"\n结论: 发现 {len(all_issues)} 处不一致（exit=1）")
        return 1

    print("\n结论: 有数据的维度按日汇总指标一致（exit=0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
