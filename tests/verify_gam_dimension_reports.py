"""
Google API（GAM）各维度报表交叉验证。

忽略 config/gam_scheduler.json 中的 report_keys 约束，强制拉取：
  - ad_unit（广告单元）
  - country（国家+广告单元）
  - site（站点+广告单元）
  - daily（按日汇总，无产品维度；有白名单时可能被跳过）

验证内容：
  1. 产品集合：ad_unit / country / site 的 product_name 是否一致
  2. 统计：country 按 (date,product,ad_unit) 汇总 == ad_unit
  3. 统计：site 按 (date,ad_unit) 汇总 == ad_unit
  4. 统计：按日汇总 ad_unit ≈ country ≈ site ≈ daily（若有）

用法：
  python tests/verify_gam_dimension_reports.py
  python tests/verify_gam_dimension_reports.py --start 2026-07-01 --end 2026-07-08
  python tests/verify_gam_dimension_reports.py --account leadwin
  python tests/verify_gam_dimension_reports.py --no-whitelist
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scheduler_module.gam_fetch import run_gam_fetch_to_memory
from app.scheduler_module.gam_import import (
    GAM_VALIDATE_METRICS,
    _filter_leaf_rows,
    validate_gam_reports,
)
from app.scheduler_module.gam_scheduler_config import get_gam_scheduler_accounts

FORCE_REPORT_KEYS = ["ad_unit", "country", "site", "daily"]
METRIC_LABELS = {
    "request_count": "请求",
    "match_count": "匹配",
    "display_count": "展示",
    "click_count": "点击",
    "revenue_before_deduct": "收益",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GAM 各维度报表交叉验证")
    p.add_argument("--start", default="2026-07-01", help="开始日期 YYYY-MM-DD")
    p.add_argument("--end", default="2026-07-08", help="结束日期 YYYY-MM-DD")
    p.add_argument("--account", default="", help="仅测指定账号 key，逗号分隔")
    p.add_argument(
        "--no-whitelist",
        action="store_true",
        help="忽略产品白名单，拉全量产品",
    )
    p.add_argument(
        "--max-detail",
        type=int,
        default=20,
        help="不一致明细最多展示条数",
    )
    return p.parse_args()


def _load_accounts(
    *,
    only_keys: set[str],
    no_whitelist: bool,
) -> list[dict[str, Any]]:
    accounts = get_gam_scheduler_accounts() or []
    if not accounts:
        raise SystemExit("未配置 GAM 账号（config/gam_scheduler.json）")

    out: list[dict[str, Any]] = []
    for acc in accounts:
        key = str(acc.get("key") or "").strip()
        if only_keys and key not in only_keys:
            continue
        item = dict(acc)
        # 强制全部维度，忽略配置里的 report_keys
        item["report_keys"] = list(FORCE_REPORT_KEYS)
        if no_whitelist:
            item["product_whitelist"] = []
        out.append(item)

    if not out:
        raise SystemExit(f"未匹配到账号: {sorted(only_keys) or '(全部)'}")
    return out


def _products(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(r.get("product_name") or "").strip().lower()
        for r in _filter_leaf_rows(rows)
        if str(r.get("product_name") or "").strip()
    }


def _day_totals(rows: list[dict[str, Any]], *, leaf_only: bool = True) -> dict[str, dict[str, float]]:
    src = _filter_leaf_rows(rows) if leaf_only else rows
    buckets: dict[str, dict[str, float]] = defaultdict(
        lambda: {m: 0.0 for m in GAM_VALIDATE_METRICS}
    )
    for row in src:
        d = str(row.get("date") or "")[:10]
        if not d:
            continue
        for m in GAM_VALIDATE_METRICS:
            buckets[d][m] += float(row.get(m) or 0)
    return dict(buckets)


def _product_day_totals(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
    buckets: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {m: 0.0 for m in GAM_VALIDATE_METRICS}
    )
    for row in _filter_leaf_rows(rows):
        d = str(row.get("date") or "")[:10]
        p = str(row.get("product_name") or "").strip().lower()
        if not d or not p:
            continue
        key = (d, p)
        for m in GAM_VALIDATE_METRICS:
            buckets[key][m] += float(row.get(m) or 0)
    return dict(buckets)


def _compare_day_maps(
    a_name: str,
    a: dict[str, dict[str, float]],
    b_name: str,
    b: dict[str, dict[str, float]],
    *,
    tolerance: float = 0.01,
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for day in sorted(set(a) | set(b)):
        left = a.get(day) or {m: 0.0 for m in GAM_VALIDATE_METRICS}
        right = b.get(day) or {m: 0.0 for m in GAM_VALIDATE_METRICS}
        issues = []
        for m in GAM_VALIDATE_METRICS:
            if abs(left[m] - right[m]) > tolerance:
                label = METRIC_LABELS.get(m, m)
                issues.append(f"{label} {left[m]:.4f} vs {right[m]:.4f}")
        if issues:
            diffs.append({"day": day, "pair": f"{a_name} vs {b_name}", "issues": issues})
    return diffs


def _compare_product_day_maps(
    a_name: str,
    a: dict[tuple[str, str], dict[str, float]],
    b_name: str,
    b: dict[tuple[str, str], dict[str, float]],
    *,
    tolerance: float = 0.01,
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for key in sorted(set(a) | set(b)):
        left = a.get(key) or {m: 0.0 for m in GAM_VALIDATE_METRICS}
        right = b.get(key) or {m: 0.0 for m in GAM_VALIDATE_METRICS}
        issues = []
        for m in GAM_VALIDATE_METRICS:
            if abs(left[m] - right[m]) > tolerance:
                label = METRIC_LABELS.get(m, m)
                issues.append(f"{label} {left[m]:.4f} vs {right[m]:.4f}")
        if issues or key not in a or key not in b:
            if key not in a:
                issues = [f"{a_name} 缺失"] + issues
            elif key not in b:
                issues = [f"{b_name} 缺失"] + issues
            diffs.append(
                {
                    "key": key,
                    "pair": f"{a_name} vs {b_name}",
                    "issues": issues,
                }
            )
    return diffs


def _sum_metrics(day_map: dict[str, dict[str, float]]) -> dict[str, float]:
    total = {m: 0.0 for m in GAM_VALIDATE_METRICS}
    for vals in day_map.values():
        for m in GAM_VALIDATE_METRICS:
            total[m] += vals[m]
    return total


def _fmt_metrics(vals: dict[str, float]) -> str:
    return (
        f"请求={vals['request_count']:.0f} "
        f"匹配={vals['match_count']:.0f} "
        f"展示={vals['display_count']:.0f} "
        f"点击={vals['click_count']:.0f} "
        f"收益={vals['revenue_before_deduct']:.4f}"
    )


def analyze_account(bundle: dict[str, Any], *, max_detail: int) -> dict[str, Any]:
    account_key = str(bundle.get("account_key") or "?")
    network = str(bundle.get("network_code") or "?")
    reports: dict[str, list] = bundle.get("reports") or {}
    warnings_fetch = list(bundle.get("warnings") or [])

    ad_unit = list(reports.get("ad_unit") or [])
    country = list(reports.get("country") or [])
    site = list(reports.get("site") or [])
    daily = list(reports.get("daily") or [])

    leaf_counts = {
        "ad_unit": len(_filter_leaf_rows(ad_unit)),
        "country": len(_filter_leaf_rows(country)),
        "site": len(_filter_leaf_rows(site)),
        "daily_raw": len(daily),
    }

    products = {
        "ad_unit": sorted(_products(ad_unit)),
        "country": sorted(_products(country)),
        "site": sorted(_products(site)),
    }
    set_au = set(products["ad_unit"])
    set_co = set(products["country"])
    set_si = set(products["site"])

    product_diff = {
        "ad_unit_only": sorted(set_au - set_co - set_si),
        "country_not_in_ad_unit": sorted(set_co - set_au),
        "site_not_in_ad_unit": sorted(set_si - set_au),
        "ad_unit_vs_country_only_left": sorted(set_au - set_co),
        "ad_unit_vs_country_only_right": sorted(set_co - set_au),
        "ad_unit_vs_site_only_left": sorted(set_au - set_si),
        "ad_unit_vs_site_only_right": sorted(set_si - set_au),
        "country_vs_site_only_left": sorted(set_co - set_si),
        "country_vs_site_only_right": sorted(set_si - set_co),
    }
    products_ok = (
        set_au == set_co == set_si
        and bool(set_au)
    ) or (not set_au and not set_co and not set_si)

    # 内置三报表校验（country/site vs ad_unit）
    built_in_warnings = validate_gam_reports(
        ad_unit, site, country, max_detail=max_detail
    )

    day_au = _day_totals(ad_unit)
    day_co = _day_totals(country)
    day_si = _day_totals(site)
    # daily 无叶子标记，直接按行汇总
    day_daily = _day_totals(daily, leaf_only=False) if daily else {}

    day_diffs: list[dict[str, Any]] = []
    day_diffs.extend(_compare_day_maps("ad_unit", day_au, "country", day_co))
    day_diffs.extend(_compare_day_maps("ad_unit", day_au, "site", day_si))
    if day_daily:
        day_diffs.extend(_compare_day_maps("ad_unit", day_au, "daily", day_daily))
        day_diffs.extend(_compare_day_maps("country", day_co, "daily", day_daily))
        day_diffs.extend(_compare_day_maps("site", day_si, "daily", day_daily))

    prod_day_au = _product_day_totals(ad_unit)
    prod_day_co = _product_day_totals(country)
    prod_day_si = _product_day_totals(site)
    prod_day_diffs: list[dict[str, Any]] = []
    prod_day_diffs.extend(
        _compare_product_day_maps("ad_unit", prod_day_au, "country", prod_day_co)
    )
    prod_day_diffs.extend(
        _compare_product_day_maps("ad_unit", prod_day_au, "site", prod_day_si)
    )
    prod_day_diffs.extend(
        _compare_product_day_maps("country", prod_day_co, "site", prod_day_si)
    )

    totals = {
        "ad_unit": _sum_metrics(day_au),
        "country": _sum_metrics(day_co),
        "site": _sum_metrics(day_si),
    }
    if day_daily:
        totals["daily"] = _sum_metrics(day_daily)

    day_table: dict[str, dict[str, dict[str, float]]] = {}
    for day in sorted(set(day_au) | set(day_co) | set(day_si) | set(day_daily)):
        day_table[day] = {
            "ad_unit": day_au.get(day) or {m: 0.0 for m in GAM_VALIDATE_METRICS},
            "country": day_co.get(day) or {m: 0.0 for m in GAM_VALIDATE_METRICS},
            "site": day_si.get(day) or {m: 0.0 for m in GAM_VALIDATE_METRICS},
        }
        if day_daily:
            day_table[day]["daily"] = day_daily.get(day) or {
                m: 0.0 for m in GAM_VALIDATE_METRICS
            }

    return {
        "account_key": account_key,
        "network_code": network,
        "fetch_warnings": warnings_fetch,
        "raw_row_counts": {k: len(v or []) for k, v in reports.items()},
        "leaf_row_counts": leaf_counts,
        "products": products,
        "product_counts": {k: len(v) for k, v in products.items()},
        "products_ok": products_ok,
        "product_diff": product_diff,
        "built_in_warnings": built_in_warnings,
        "built_in_ok": not built_in_warnings,
        "day_ok": not day_diffs,
        "day_diff_count": len(day_diffs),
        "day_diffs": day_diffs[:max_detail],
        "product_day_ok": not prod_day_diffs,
        "product_day_diff_count": len(prod_day_diffs),
        "product_day_diffs": prod_day_diffs[:max_detail],
        "totals": totals,
        "day_table": {
            d: {rk: {m: round(vv[m], 4) for m in GAM_VALIDATE_METRICS} for rk, vv in reps.items()}
            for d, reps in day_table.items()
        },
        "overall_ok": (
            products_ok
            and not built_in_warnings
            and not day_diffs
            and not prod_day_diffs
            and bool(ad_unit or country or site)
        ),
    }


def print_account_report(result: dict[str, Any]) -> None:
    print("\n" + "=" * 100)
    print(f"账号 {result['account_key']} / 网络 {result['network_code']}")
    print("=" * 100)

    if result["fetch_warnings"]:
        print("拉数告警:")
        for w in result["fetch_warnings"]:
            print(f"  - {w}")

    print("\n【行数】")
    print(f"  原始: {result['raw_row_counts']}")
    print(f"  叶子: {result['leaf_row_counts']}")

    print("\n【产品集合】")
    for name, items in result["products"].items():
        print(f"  {name}: {len(items)} 个 → {items}")
    print(f"  产品集合一致: {'是' if result['products_ok'] else '否'}")
    if not result["products_ok"]:
        pd = result["product_diff"]
        for label, keys in [
            ("ad_unit 有而 country 无", pd["ad_unit_vs_country_only_left"]),
            ("country 有而 ad_unit 无", pd["ad_unit_vs_country_only_right"]),
            ("ad_unit 有而 site 无", pd["ad_unit_vs_site_only_left"]),
            ("site 有而 ad_unit 无", pd["ad_unit_vs_site_only_right"]),
            ("country 有而 site 无", pd["country_vs_site_only_left"]),
            ("site 有而 country 无", pd["country_vs_site_only_right"]),
        ]:
            if keys:
                print(f"  {label}: {keys}")

    print("\n【区间总汇总】")
    for name, vals in result["totals"].items():
        print(f"  {name:<10} {_fmt_metrics(vals)}")

    print("\n【按日汇总对照】")
    header = (
        f"{'日期':<12} {'报表':<10} {'请求':>12} {'匹配':>12} "
        f"{'展示':>12} {'点击':>10} {'收益':>12}"
    )
    print(header)
    print("-" * len(header))
    for day, reps in result["day_table"].items():
        for rk, vals in reps.items():
            print(
                f"{day:<12} {rk:<10} "
                f"{vals['request_count']:>12.0f} {vals['match_count']:>12.0f} "
                f"{vals['display_count']:>12.0f} {vals['click_count']:>10.0f} "
                f"{vals['revenue_before_deduct']:>12.4f}"
            )
        print("-" * len(header))

    print("\n【内置交叉校验 country/site vs ad_unit】")
    if result["built_in_ok"]:
        print("  通过：country/site 与 ad_unit 全部对齐")
    else:
        for w in result["built_in_warnings"]:
            print(f"  - {w}")

    print("\n【按日交叉】")
    if result["day_ok"]:
        print("  结果: 一致")
    else:
        print(f"  结果: 不一致 {result['day_diff_count']} 项")
    for d in result["day_diffs"]:
        print(f"  {d['pair']} {d['day']}: {'; '.join(d['issues'])}")

    print("\n【按日期+产品交叉】")
    if result["product_day_ok"]:
        print("  结果: 一致")
    else:
        print(f"  结果: 不一致 {result['product_day_diff_count']} 项")
    for d in result["product_day_diffs"][:20]:
        print(f"  {d['pair']} {d['key']}: {'; '.join(d['issues'])}")

    print(f"\n【账号结论】{'通过' if result['overall_ok'] else '未通过'}")


async def main() -> int:
    args = _parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    only = {x.strip() for x in args.account.split(",") if x.strip()}

    accounts = _load_accounts(only_keys=only, no_whitelist=args.no_whitelist)

    print("=" * 100)
    print("Google API（GAM）各维度报表交叉验证")
    print("=" * 100)
    print(f"区间: {start.isoformat()} ~ {end.isoformat()}")
    print(f"强制报表: {FORCE_REPORT_KEYS}（忽略配置 report_keys）")
    print(f"忽略白名单: {args.no_whitelist}")
    print("账号:")
    for acc in accounts:
        print(
            f"  - {acc.get('key')} report_keys={acc.get('report_keys')} "
            f"whitelist={acc.get('product_whitelist') or '[](全量)'}"
        )

    print("\n>>> 开始拉数（可能较慢）...")
    # run_gam_fetch_to_memory 是同步阻塞（googleads SOAP）
    bundles = await asyncio.to_thread(
        run_gam_fetch_to_memory,
        start,
        end,
        report_keys=FORCE_REPORT_KEYS,
        accounts=accounts,
    )
    print(f">>> 拉数完成，账号数={len(bundles)}")

    results = [analyze_account(b, max_detail=args.max_detail) for b in bundles]
    for r in results:
        print_account_report(r)

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "forced_report_keys": FORCE_REPORT_KEYS,
        "no_whitelist": args.no_whitelist,
        "accounts": results,
        "all_ok": all(r["overall_ok"] for r in results) if results else False,
    }
    out_path = ROOT / "tests" / "_gam_dimension_verify_result.json"
    # day_table 可能较大，完整写入
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n摘要已写入: {out_path}")

    print("\n" + "=" * 100)
    if not results:
        print("结论: 无账号数据")
        return 3
    if out["all_ok"]:
        print("结论: 全部账号各维度产品与统计数据一致。")
        return 0
    failed = [r["account_key"] for r in results if not r["overall_ok"]]
    print(f"结论: 存在不一致账号: {failed}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
