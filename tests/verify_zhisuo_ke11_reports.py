"""
KE11 智索报表交叉验证（忽略 .env 拉数开关）

本脚本只读取账号凭证（client_id / api_key / base_url），
**不读取、不遵守** 以下 .env 约束：
  - ZHISUO_API_FETCH_UNIT
  - ZHISUO_API_FETCH_COUNTRY
  - ZHISUO_API_FETCH_DATA
  - ZHISUO_API_FETCH_DAILY_FALLBACK
  - ZHISUO_API_ACCOUNT_FETCH

强制拉取全部报表并相互核对：
  - channeldaily（日报）
  - channelcountry（国家）
  - channelunit（广告单元）
  - channeldata（国家+广告单元交叉）

验证维度：
  1. 按「日期」汇总指标一致
  2. 按「日期+产品」汇总指标一致
  3. 产品日覆盖集合一致

用法：
  python tests/verify_zhisuo_ke11_reports.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.scheduler_module.upstream_fetch import (
    ZHISUO_COUNTRY_PATH,
    ZHISUO_DAILY_PATH,
    ZHISUO_DATA_PATH,
    ZHISUO_UNIT_PATH,
    fetch_zhisuo_report_rows,
)

START = "2026-07-01"
END = "2026-07-08"
CLIENT_ID = "KE11"

INT_TOL = 0
REV_TOL = 0.02

# 强制拉取的全部报表（与 .env fetch_* 无关）
FORCE_REPORTS: list[tuple[str, str, str]] = [
    ("daily", ZHISUO_DAILY_PATH, "日报 channeldaily"),
    ("country", ZHISUO_COUNTRY_PATH, "国家 channelcountry"),
    ("unit", ZHISUO_UNIT_PATH, "单元 channelunit"),
    ("cross", ZHISUO_DATA_PATH, "交叉 channeldata"),
]

# 兼容旧路径探测（正式路径为 channeldata）
CROSS_PATH_FALLBACKS = [
    "/api/channelcountryandunit",
    "/api/channelcountryunit",
    "/api/channelunitandcountry",
    "/api/channelCountryAndUnit",
]


@dataclass
class Agg:
    request: int = 0
    match: int = 0
    display: int = 0
    click: int = 0
    revenue: float = 0.0
    rows: int = 0

    def add_row(self, row: dict[str, Any]) -> None:
        self.request += int(row.get("ad_requests") or 0)
        self.match += int(row.get("matched_requests") or 0)
        self.display += int(row.get("ad_impressions") or 0)
        self.click += int(row.get("clicks") or 0)
        self.revenue += float(row.get("estimated_earnings") or 0)
        self.rows += 1

    def as_tuple(self) -> tuple:
        return (
            self.request,
            self.match,
            self.display,
            self.click,
            round(self.revenue, 4),
            self.rows,
        )


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _i(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": str(row.get("date") or "").strip()[:10],
        "domain_name": str(row.get("domain_name") or "").strip().lower(),
        "country": str(row.get("country") or row.get("country_code") or "").strip().upper(),
        "ad_unit_name": str(row.get("ad_unit_name") or row.get("ad_unit") or "").strip(),
        "ad_requests": _i(row.get("ad_requests")),
        "matched_requests": _i(row.get("matched_requests")),
        "ad_impressions": _i(row.get("ad_impressions")),
        "clicks": _i(row.get("clicks")),
        "estimated_earnings": _f(row.get("estimated_earnings")),
    }


def aggregate(
    rows: list[dict[str, Any]],
    *,
    by_product: bool = False,
) -> dict[tuple, Agg]:
    out: dict[tuple, Agg] = defaultdict(Agg)
    for raw in rows:
        r = normalize_row(raw)
        if not r["date"]:
            continue
        key = (r["date"], r["domain_name"]) if by_product else (r["date"],)
        out[key].add_row(r)
    return dict(out)


def compare_aggs(
    name_a: str,
    a: dict[tuple, Agg],
    name_b: str,
    b: dict[tuple, Agg],
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for key in sorted(set(a) | set(b)):
        left = a.get(key) or Agg()
        right = b.get(key) or Agg()
        issues = []
        if abs(left.request - right.request) > INT_TOL:
            issues.append(f"请求 {left.request} vs {right.request}")
        if abs(left.match - right.match) > INT_TOL:
            issues.append(f"匹配 {left.match} vs {right.match}")
        if abs(left.display - right.display) > INT_TOL:
            issues.append(f"展示 {left.display} vs {right.display}")
        if abs(left.click - right.click) > INT_TOL:
            issues.append(f"点击 {left.click} vs {right.click}")
        if abs(left.revenue - right.revenue) > REV_TOL:
            issues.append(f"收益 {left.revenue:.4f} vs {right.revenue:.4f}")
        if issues:
            diffs.append(
                {
                    "key": key,
                    "pair": f"{name_a} vs {name_b}",
                    "issues": issues,
                    "a": left.as_tuple(),
                    "b": right.as_tuple(),
                }
            )
    return diffs


def find_ke11_account() -> tuple[str, str, str, dict[str, Any]]:
    """只取凭证；返回账号上的 fetch_* 仅用于打印对比，不参与拉数决策。"""
    accounts = settings.get_zhisuo_accounts()
    for acc in accounts:
        cid = str(acc.get("client_id") or "").strip()
        if cid == CLIENT_ID:
            key = str(acc.get("api_key") or "").strip()
            if not key:
                raise SystemExit(f"账号 {CLIENT_ID} 未配置 api_key")
            return cid, key, settings.ZHISUO_API_BASE_URL.rstrip("/"), dict(acc)
    raise SystemExit(f"未找到账号 {CLIENT_ID}，请检查 .env 凭证")


def print_env_ignored(account: dict[str, Any]) -> None:
    print("=" * 100)
    print("【忽略 .env 拉数约束】本测试强制拉取全部报表")
    print("=" * 100)
    print(
        f"  .env 全局: FETCH_UNIT={settings.ZHISUO_API_FETCH_UNIT} "
        f"FETCH_COUNTRY={settings.ZHISUO_API_FETCH_COUNTRY} "
        f"FETCH_DATA={settings.ZHISUO_API_FETCH_DATA} "
        f"FETCH_DAILY_FALLBACK={settings.ZHISUO_API_FETCH_DAILY_FALLBACK}"
    )
    print(
        f"  账号 {CLIENT_ID} 配置: fetch_unit={account.get('fetch_unit')} "
        f"fetch_country={account.get('fetch_country')} "
        f"fetch_data={account.get('fetch_data')} "
        f"fetch_daily_fallback={account.get('fetch_daily_fallback')}"
    )
    print("  本脚本实际强制拉取: daily + country + unit + cross(channeldata)")
    print("  （不按上述开关过滤）")


async def fetch_one(
    *,
    base_url: str,
    client_id: str,
    api_key: str,
    name: str,
    path: str,
    label: str,
) -> list[dict[str, Any]]:
    print(f"\n>>> 强制拉取 {label} ({START} ~ {END}) path={path}")
    fr = await fetch_zhisuo_report_rows(
        base_url=base_url,
        client_id=client_id,
        api_key=api_key,
        start=START,
        end=END,
        path=path,
        label=label,
        limit=1000,
        per_day=True,
    )
    rows = [r for r in fr.rows if isinstance(r, dict)]
    print(
        f"    行数={len(rows)}, pages={fr.stats.pages_fetched}, "
        f"api_total≈{fr.stats.total_rows}"
    )
    if rows:
        sample = normalize_row(rows[0])
        print(
            f"    样例: date={sample['date']}, domain={sample['domain_name']!r}, "
            f"country={sample['country']!r}, unit={sample['ad_unit_name']!r}"
        )
    return rows


async def fetch_cross_with_fallback(
    *,
    base_url: str,
    client_id: str,
    api_key: str,
) -> tuple[list[dict[str, Any]], str]:
    """优先 channeldata；失败时尝试旧交叉路径。"""
    primary = ZHISUO_DATA_PATH
    try:
        rows = await fetch_one(
            base_url=base_url,
            client_id=client_id,
            api_key=api_key,
            name="cross",
            path=primary,
            label="交叉 channeldata",
        )
        return rows, primary
    except Exception as e:
        print(f"    channeldata 失败: {str(e).splitlines()[0][:120]}")

    for path in CROSS_PATH_FALLBACKS:
        label = f"交叉回退 {path}"
        print(f"\n>>> 尝试 {label} ...")
        try:
            await fetch_zhisuo_report_rows(
                base_url=base_url,
                client_id=client_id,
                api_key=api_key,
                start=START,
                end=START,
                path=path,
                label=label,
                limit=1000,
                per_day=False,
            )
            fr = await fetch_zhisuo_report_rows(
                base_url=base_url,
                client_id=client_id,
                api_key=api_key,
                start=START,
                end=END,
                path=path,
                label=label,
                limit=1000,
                per_day=True,
            )
            rows = [r for r in fr.rows if isinstance(r, dict)]
            print(f"    成功 path={path} 行数={len(rows)}")
            return rows, path
        except Exception as err:
            print(f"    失败 path={path}: {str(err).splitlines()[0][:120]}")
    print("\n!!! 交叉报表接口不可用，cross 记为空")
    return [], primary


async def fetch_all_forced(
    base_url: str, client_id: str, api_key: str
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for name, path, label in FORCE_REPORTS:
        if name == "cross":
            continue
        result[name] = await fetch_one(
            base_url=base_url,
            client_id=client_id,
            api_key=api_key,
            name=name,
            path=path,
            label=label,
        )
    cross_rows, _ = await fetch_cross_with_fallback(
        base_url=base_url, client_id=client_id, api_key=api_key
    )
    result["cross"] = cross_rows
    return result


def active_report_names(rows_map: dict[str, list]) -> list[str]:
    # daily/country/unit 即使 0 行也参与；cross 仅有数据时参与核对
    names = [n for n, _, _ in FORCE_REPORTS if n != "cross"]
    if rows_map.get("cross"):
        names.append("cross")
    return names


def build_pairs(names: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pairs.append((a, b))
    return pairs


def print_day_table(aggs: dict[str, dict[tuple, Agg]], names: list[str]) -> None:
    print("\n" + "=" * 100)
    print("【按日汇总】请求 / 匹配 / 展示 / 点击 / 收益 / 行数")
    print("=" * 100)
    dates = sorted({k[0] for a in aggs.values() for k in a})
    header = (
        f"{'日期':<12} {'报表':<10} {'请求':>12} {'匹配':>12} "
        f"{'展示':>12} {'点击':>10} {'收益':>12} {'行数':>6}"
    )
    print(header)
    print("-" * len(header))
    for d in dates:
        for name in names:
            a = aggs[name].get((d,)) or Agg()
            print(
                f"{d:<12} {name:<10} {a.request:>12} {a.match:>12} {a.display:>12} "
                f"{a.click:>10} {a.revenue:>12.4f} {a.rows:>6}"
            )
        print("-" * len(header))


def grand_totals(aggs: dict[str, dict[tuple, Agg]], names: list[str]) -> None:
    print("\n" + "=" * 100)
    print(f"【区间总汇总】{START} ~ {END}")
    print("=" * 100)
    for name in names:
        total = Agg()
        for a in aggs[name].values():
            total.request += a.request
            total.match += a.match
            total.display += a.display
            total.click += a.click
            total.revenue += a.revenue
            total.rows += a.rows
        print(
            f"  {name:<10} 请求={total.request:>12} 匹配={total.match:>12} "
            f"展示={total.display:>12} 点击={total.click:>10} "
            f"收益={total.revenue:>12.4f} 行数={total.rows}"
        )


def coverage_report(rows_map: dict[str, list[dict[str, Any]]]) -> None:
    print("\n" + "=" * 100)
    print("【产品日覆盖】各报表 (date, domain) 集合差集")
    print("=" * 100)
    sets: dict[str, set[tuple[str, str]]] = {}
    for name, rows in rows_map.items():
        s: set[tuple[str, str]] = set()
        for raw in rows:
            r = normalize_row(raw)
            if r["date"] and r["domain_name"]:
                s.add((r["date"], r["domain_name"]))
        sets[name] = s
        print(f"  {name}: {len(s)} 个产品日")

    names = list(sets.keys())
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            only_a = sorted(sets[a] - sets[b])
            only_b = sorted(sets[b] - sets[a])
            print(f"\n  {a} 有而 {b} 无: {len(only_a)}")
            for item in only_a[:15]:
                print(f"    {item}")
            if len(only_a) > 15:
                print(f"    ... +{len(only_a) - 15}")
            print(f"  {b} 有而 {a} 无: {len(only_b)}")
            for item in only_b[:15]:
                print(f"    {item}")
            if len(only_b) > 15:
                print(f"    ... +{len(only_b) - 15}")


def print_product_day_mismatches(diffs: list[dict[str, Any]], limit: int = 40) -> None:
    print("\n" + "=" * 100)
    print(f"【日期+产品 不一致明细】共 {len(diffs)} 条（最多展示 {limit}）")
    print("=" * 100)
    for i, d in enumerate(diffs[:limit]):
        print(f"\n#{i + 1} {d['pair']}  key={d['key']}")
        for issue in d["issues"]:
            print(f"    - {issue}")
        print(f"    A={d['a']}")
        print(f"    B={d['b']}")
    if len(diffs) > limit:
        print(f"\n... 另有 {len(diffs) - limit} 条未展示")


async def main() -> int:
    client_id, api_key, base_url, account = find_ke11_account()
    print(f"账号={client_id} base={base_url} 区间={START}~{END}")
    print_env_ignored(account)

    rows_map = await fetch_all_forced(base_url, client_id, api_key)
    names = active_report_names(rows_map)
    print(f"\n参与交叉验证的报表: {names}")
    print(f"行数: " + ", ".join(f"{n}={len(rows_map.get(n) or [])}" for n in ("daily", "country", "unit", "cross")))

    # 强制报表必须拉到数据，否则视为失败
    for name, _, _ in FORCE_REPORTS:
        if not rows_map.get(name):
            print(f"\n错误: 强制报表 {name} 无数据，无法交叉验证")
            return 3

    aggs_day = {name: aggregate(rows_map[name], by_product=False) for name in names}
    aggs_prod = {name: aggregate(rows_map[name], by_product=True) for name in names}

    print_day_table(aggs_day, names)
    grand_totals(aggs_day, names)
    coverage_report({n: rows_map[n] for n in names})

    day_pairs = build_pairs(names)

    print("\n" + "=" * 100)
    print("【按日交叉验证结果】")
    print("=" * 100)
    day_all_ok = True
    day_diff_count = 0
    for a, b in day_pairs:
        diffs = compare_aggs(a, aggs_day[a], b, aggs_day[b])
        status = "一致" if not diffs else f"不一致 {len(diffs)} 天"
        print(f"  {a} vs {b}: {status}")
        if diffs:
            day_all_ok = False
            day_diff_count += len(diffs)
            for d in diffs:
                print(f"    {d['key'][0]}: {'; '.join(d['issues'])}")

    print("\n" + "=" * 100)
    print("【按日期+产品交叉验证结果】")
    print("=" * 100)
    prod_all_ok = True
    all_prod_diffs: list[dict[str, Any]] = []
    for a, b in day_pairs:
        diffs = compare_aggs(a, aggs_prod[a], b, aggs_prod[b])
        status = "一致" if not diffs else f"不一致 {len(diffs)} 组"
        print(f"  {a} vs {b}: {status}")
        if diffs:
            prod_all_ok = False
            all_prod_diffs.extend(diffs)

    print_product_day_mismatches(all_prod_diffs)

    out_path = ROOT / "tests" / "_zhisuo_ke11_verify_result.json"
    summary = {
        "client_id": client_id,
        "start": START,
        "end": END,
        "ignored_env_fetch_flags": True,
        "env_fetch_unit": settings.ZHISUO_API_FETCH_UNIT,
        "env_fetch_country": settings.ZHISUO_API_FETCH_COUNTRY,
        "env_fetch_data": settings.ZHISUO_API_FETCH_DATA,
        "env_fetch_daily_fallback": settings.ZHISUO_API_FETCH_DAILY_FALLBACK,
        "account_fetch": {
            "fetch_unit": account.get("fetch_unit"),
            "fetch_country": account.get("fetch_country"),
            "fetch_data": account.get("fetch_data"),
            "fetch_daily_fallback": account.get("fetch_daily_fallback"),
        },
        "forced_reports": [n for n, _, _ in FORCE_REPORTS],
        "reports_verified": names,
        "row_counts": {k: len(v) for k, v in rows_map.items()},
        "cross_available": bool(rows_map.get("cross")),
        "day_ok": day_all_ok,
        "product_day_ok": prod_all_ok,
        "day_diff_pairs": day_diff_count,
        "product_day_diff_count": len(all_prod_diffs),
        "day_totals": {
            name: {
                d[0]: (aggs_day[name].get(d) or Agg()).as_tuple()
                for d in sorted(aggs_day[name])
            }
            for name in names
        },
        "sample_product_diffs": all_prod_diffs[:50],
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n摘要已写入: {out_path}")

    print("\n" + "=" * 100)
    if not rows_map.get("cross"):
        print("说明: 交叉报表 channeldata（及旧路径回退）不可用，未纳入核对。")
    if day_all_ok and prod_all_ok:
        print(f"结论: 强制拉取的报表 {names} 在「按日」与「按日期+产品」维度全部一致。")
        return 0
    if day_all_ok and not prod_all_ok:
        print("结论: 按日汇总一致，但部分「日期+产品」明细不一致。")
        return 1
    print("结论: 存在按日汇总不一致。")
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
